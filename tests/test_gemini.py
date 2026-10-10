from __future__ import annotations

import fcntl
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import app
from backend import gemini
from backend.config import events_path
from backend.db import connect
from backend.reconcile import process_alive, living_sessions, reconcile
from hooks import capture


def at(minutes: int) -> str:
    now = datetime.now(timezone.utc)
    return (now + timedelta(minutes=minutes)).isoformat(timespec="seconds")


@pytest.fixture
def gemini_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data"
    gemini_dir = tmp_path / "gemini"
    presence_dir = gemini_dir / "presence"
    config_dir = tmp_path / "config"

    data_dir.mkdir(parents=True)
    gemini_dir.mkdir(parents=True)
    presence_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)

    monkeypatch.setenv("AI_OPERATIONS_ROOM_DATA_DIR", str(data_dir))
    monkeypatch.setenv("GEMINI_DATA_DIR", str(gemini_dir))
    monkeypatch.setenv("GEMINI_CONFIG_DIR", str(config_dir))

    # Initialize Gemini mock conversation db
    db_file = gemini_dir / "conversation_summaries.db"
    with sqlite3.connect(db_file) as con:
        con.execute("""
            CREATE TABLE conversation_summaries (
                conversation_id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                preview TEXT NOT NULL DEFAULT '',
                step_count INTEGER NOT NULL DEFAULT 0,
                last_modified_time DATETIME NOT NULL,
                workspace_uris TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                project_id TEXT NOT NULL DEFAULT '',
                agent_name TEXT NOT NULL DEFAULT '',
                parent_conversation_id TEXT NOT NULL DEFAULT '',
                nesting_depth INTEGER NOT NULL DEFAULT 0,
                battle_id TEXT NOT NULL DEFAULT '',
                winning_conversation_id TEXT NOT NULL DEFAULT '',
                not_fully_idle NUMERIC NOT NULL DEFAULT 0,
                killed NUMERIC NOT NULL DEFAULT 0,
                last_user_input_time DATETIME NOT NULL,
                last_user_input_step_index INTEGER NOT NULL DEFAULT -1,
                app_data_dir TEXT NOT NULL DEFAULT '',
                raw_summary BLOB,
                group_id TEXT NOT NULL DEFAULT ''
            );
        """)

    return {
        "data_dir": data_dir,
        "gemini_dir": gemini_dir,
        "presence_dir": presence_dir,
        "config_dir": config_dir,
        "db_file": db_file,
    }


def test_parse_cwd():
    assert gemini.parse_cwd("file:///Users/test/project") == "/Users/test/project"
    assert gemini.parse_cwd('["file:///Users/test/project"]') == "/Users/test/project"
    assert gemini.parse_cwd(["/Users/test/project"]) == "/Users/test/project"
    assert gemini.parse_cwd("") == ""


def test_presence_lock_active_and_inactive(gemini_env):
    presence_dir = gemini_env["presence_dir"]
    cid = "test-session-123"
    lock_file = presence_dir / f"{cid}.lock"

    # No file: inactive
    assert not gemini.is_session_active(cid)

    # File exists and unheld: inactive
    lock_file.touch()
    assert not gemini.is_session_active(cid)

    # File held by process: active
    with lock_file.open("r") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert gemini.is_session_active(cid)
        fcntl.flock(f, fcntl.LOCK_UN)

    # Released: inactive again
    assert not gemini.is_session_active(cid)


def test_gemini_sync_projects_runs(gemini_env):
    db_file = gemini_env["db_file"]
    presence_dir = gemini_env["presence_dir"]

    # Insert an active running conversation and an idle conversation
    now_ts = at(0)
    with sqlite3.connect(db_file) as con:
        con.execute("""
            INSERT INTO conversation_summaries
            (conversation_id, title, status, last_modified_time, workspace_uris, not_fully_idle, last_user_input_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("sess-active", "Working Session", "CASCADE_RUN_STATUS_RUNNING", now_ts,
              json.dumps(["file:///projects/atlas"]), 1, now_ts))
        con.execute("""
            INSERT INTO conversation_summaries
            (conversation_id, title, status, last_modified_time, workspace_uris, not_fully_idle, last_user_input_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("sess-idle", "Idle Session", "CASCADE_RUN_STATUS_IDLE", now_ts,
              json.dumps(["file:///projects/orion"]), 0, at(-5)))

    # Hold lock for active session
    active_lock = presence_dir / "sess-active.lock"
    active_lock.touch()
    with active_lock.open("r") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)

        with TestClient(app) as client:
            resp = client.get("/api/painel").json()
            runs = {r["session_id"]: r["estado"] for r in resp["execucoes"]}
            assert runs.get("sess-active") == "trabalhando"
            # sess-idle is not locked, so it's marked as concluida
            assert runs.get("sess-idle") == "concluida"

        fcntl.flock(f, fcntl.LOCK_UN)


def test_gemini_sync_with_subagent(gemini_env):
    db_file = gemini_env["db_file"]
    presence_dir = gemini_env["presence_dir"]

    now_ts = at(0)
    with sqlite3.connect(db_file) as con:
        # Parent conversation
        con.execute("""
            INSERT INTO conversation_summaries
            (conversation_id, title, status, last_modified_time, workspace_uris, not_fully_idle, last_user_input_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("parent-1", "Lead Dev", "CASCADE_RUN_STATUS_RUNNING", now_ts,
              json.dumps(["file:///projects/atlas"]), 1, now_ts))
        # Child subagent conversation
        con.execute("""
            INSERT INTO conversation_summaries
            (conversation_id, parent_conversation_id, agent_name, title, status, last_modified_time, workspace_uris, not_fully_idle, last_user_input_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("child-1", "parent-1", "Code Reviewer", "Reviewing PR", "CASCADE_RUN_STATUS_RUNNING", now_ts,
              json.dumps(["file:///projects/atlas"]), 1, now_ts))

    lock_parent = presence_dir / "parent-1.lock"
    lock_child = presence_dir / "child-1.lock"
    lock_parent.touch()
    lock_child.touch()

    with lock_parent.open("r") as fp, lock_child.open("r") as fc:
        fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fc, fcntl.LOCK_EX | fcntl.LOCK_NB)

        with TestClient(app) as client:
            panel = client.get("/api/painel").json()
            states = {item["chave"]: (item["estado"], item["tipo"]) for item in panel["execucoes"]}
            # Parent is delegating because child is active
            assert states["session:parent-1"][0] == "delegando"
            # Child is working
            assert states["agent:child-1"] == ("trabalhando", "Code Reviewer")

        fcntl.flock(fp, fcntl.LOCK_UN)
        fcntl.flock(fc, fcntl.LOCK_UN)


def test_gemini_hooks_install_and_remove(gemini_env):
    config_dir = gemini_env["config_dir"]
    hooks_path = config_dir / "hooks.json"

    gemini.install_hooks(hooks_path)
    assert hooks_path.exists()
    data = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert "ai-operations-room" in data
    assert "PreInvocation" in data["ai-operations-room"]
    assert "Stop" in data["ai-operations-room"]

    gemini.remove_hooks(hooks_path)
    data = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert "ai-operations-room" not in data


def test_capture_script_gemini_payload(gemini_env, monkeypatch):
    data_dir = gemini_env["data_dir"]
    monkeypatch.setenv("AI_OPERATIONS_ROOM_DATA_DIR", str(data_dir))

    # Test PreInvocation payload
    payload = {
        "conversationId": "gemini-conv-01",
        "workspacePaths": ["/Users/carlos/Projects/app"],
        "modelName": "auto",
    }
    normalized = capture.normalize(payload, "PreInvocation")
    assert normalized["session_id"] == "gemini-conv-01"
    assert normalized["evento"] == "UserPromptSubmit"
    assert normalized["cwd"] == "/Users/carlos/Projects/app"

    # Test subagent call
    sub_payload = {
        "conversationId": "gemini-conv-01",
        "workspacePaths": ["/Users/carlos/Projects/app"],
        "toolCall": {
            "name": "invoke_subagent",
            "args": {
                "Subagents": [{"Role": "Database Debugger", "TypeName": "debugger"}]
            }
        }
    }
    sub_norm = capture.normalize(sub_payload, "SubagentStart")
    assert sub_norm["evento"] == "SubagentStart"
    assert sub_norm["agent_type"] == "Database Debugger"
