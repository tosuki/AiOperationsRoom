"""Gemini / agy observer, data sync and lifecycle hooks."""

from __future__ import annotations

import fcntl
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from backend.config import ROOT, data_dir


def gemini_data_dir() -> Path:
    if os.environ.get("GEMINI_DATA_DIR"):
        return Path(os.environ["GEMINI_DATA_DIR"]).expanduser()
    if os.environ.get("AI_OPERATIONS_ROOM_DATA_DIR"):
        return Path(os.environ["AI_OPERATIONS_ROOM_DATA_DIR"]).expanduser() / "gemini"
    return (Path.home() / ".gemini" / "antigravity-cli").expanduser()


def gemini_config_dir() -> Path:
    return Path(
        os.environ.get("GEMINI_CONFIG_DIR")
        or Path.home() / ".gemini" / "config"
    ).expanduser()


def gemini_db_path() -> Path:
    return gemini_data_dir() / "conversation_summaries.db"


def gemini_presence_dir() -> Path:
    return gemini_data_dir() / "presence"


def is_session_active(conversation_id: str) -> bool:
    """Check if the session has an active process holding its presence lock."""
    lock_file = gemini_presence_dir() / f"{conversation_id}.lock"
    if not lock_file.exists():
        return False
    try:
        with lock_file.open("r", encoding="utf-8") as f:
            if sys.platform != "win32":
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(f, fcntl.LOCK_UN)
                    return False
                except (BlockingIOError, PermissionError):
                    return True
            else:
                try:
                    import msvcrt
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                    return False
                except (OSError, PermissionError):
                    return True
    except OSError:
        return False


def parse_cwd(raw_uris: object) -> str:
    if isinstance(raw_uris, str):
        try:
            uris = json.loads(raw_uris)
        except (json.JSONDecodeError, UnicodeError):
            uris = [raw_uris]
    elif isinstance(raw_uris, list):
        uris = raw_uris
    else:
        uris = []

    if not uris:
        return ""
    first = uris[0] if isinstance(uris, list) and uris else str(uris)
    if isinstance(first, str) and first.startswith("file://"):
        return unquote(urlparse(first).path)
    return str(first) if first else ""


def normalize_iso(ts: str | None) -> str:
    if not ts:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    clean = ts.replace(" ", "T").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat(timespec="seconds")
    except (ValueError, TypeError):
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sync_gemini(con: sqlite3.Connection) -> int:
    """Sync conversations and executions directly from Gemini/agy local database."""
    if (data_dir() / ".demo-mode").exists():
        return 0

    db_file = gemini_db_path()
    if not db_file.exists():
        return 0

    uri = f"file:{db_file.resolve()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5) as g_con:
            g_con.row_factory = sqlite3.Row
            rows = g_con.execute("""
                SELECT conversation_id, title, status, last_modified_time,
                       workspace_uris, agent_name, parent_conversation_id,
                       not_fully_idle, killed, last_user_input_time
                FROM conversation_summaries
                ORDER BY last_modified_time DESC LIMIT 100
            """).fetchall()
    except Exception:
        return 0

    processed = 0

    active_children_by_parent: dict[str, list[str]] = {}
    parsed_rows = []

    for row in rows:
        cid = row["conversation_id"]
        if not cid:
            continue
        parent_id = row["parent_conversation_id"] or None
        active = is_session_active(cid)
        if active and parent_id:
            active_children_by_parent.setdefault(parent_id, []).append(cid)
        parsed_rows.append((row, cid, parent_id, active))

    for row, cid, parent_id, active in parsed_rows:
        cwd = parse_cwd(row["workspace_uris"])
        last_mod = normalize_iso(row["last_modified_time"])
        last_input = normalize_iso(row["last_user_input_time"]) if row["last_user_input_time"] else last_mod

        status_str = row["status"] or ""
        not_idle = bool(row["not_fully_idle"])
        killed = bool(row["killed"])

        if active:
            if not_idle or status_str == "CASCADE_RUN_STATUS_RUNNING":
                if parent_id is None and active_children_by_parent.get(cid):
                    state = "delegando"
                else:
                    state = "trabalhando"
            else:
                state = "aguardando"
            origem = None
        else:
            if killed:
                state = "orfa"
                origem = "pid_morto"
            else:
                state = "concluida"
                origem = "SessionEnd"

        key = f"agent:{cid}" if parent_id else f"session:{cid}"
        parent_key = f"session:{parent_id}" if parent_id else None
        agent_type = row["agent_name"] or ("subagente" if parent_id else "principal")

        existing = con.execute("SELECT atualizado_em, estado FROM execucao WHERE chave = ?", (key,)).fetchone()
        if existing and existing["atualizado_em"] > last_mod and existing["estado"] == state:
            continue

        session_owner = parent_id if parent_id else cid

        con.execute("""
            INSERT INTO execucao (chave, session_id, agent_id, pai_chave, tipo, cwd, estado,
                                  origem_encerramento, criado_em, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chave) DO UPDATE SET
                cwd = CASE WHEN excluded.cwd <> '' THEN excluded.cwd ELSE execucao.cwd END,
                estado = excluded.estado,
                origem_encerramento = excluded.origem_encerramento,
                atualizado_em = excluded.atualizado_em
        """, (
            key,
            session_owner,
            cid if parent_id else None,
            parent_key,
            agent_type,
            cwd,
            state,
            origem,
            last_input,
            last_mod,
        ))

        if cwd and not parent_id:
            con.execute("""
                INSERT INTO sessao (session_id, cwd, ultimo_evento, ultima_atualizacao)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    cwd = CASE WHEN excluded.ultima_atualizacao >= sessao.ultima_atualizacao
                        AND excluded.cwd <> '' THEN excluded.cwd ELSE sessao.cwd END,
                    ultimo_evento = CASE WHEN excluded.ultima_atualizacao >= sessao.ultima_atualizacao
                        THEN excluded.ultimo_evento ELSE sessao.ultimo_evento END,
                    ultima_atualizacao = MAX(sessao.ultima_atualizacao, excluded.ultima_atualizacao)
            """, (cid, cwd, state, last_mod))

        ev_id = f"gemini-sync-{cid}"
        title = row["title"] or "Sessão Gemini"
        con.execute("""
            INSERT OR IGNORE INTO evento (id, session_id, nome, ocorrido_em, dados)
            VALUES (?, ?, ?, ?, ?)
        """, (
            ev_id,
            session_owner,
            "SessionStart" if state == "aguardando" else ("UserPromptSubmit" if state in ("trabalhando", "delegando") else "Stop"),
            last_mod,
            json.dumps({"title": title, "status": status_str, "agent": agent_type}, ensure_ascii=False)
        ))

        processed += 1

    return processed


def hooks_file_path() -> Path:
    return gemini_config_dir() / "hooks.json"


def capture_command(event_name: str) -> str:
    invocation = f'"{sys.executable}" "{ROOT / "hooks" / "capture.py"}" {event_name}'
    return f"& {invocation}" if os.name == "nt" else invocation


def install_hooks(path: Path | None = None) -> None:
    path = path or hooks_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    entry = {
        "PreInvocation": [
            {"type": "command", "command": capture_command("PreInvocation"), "timeout": 5}
        ],
        "Stop": [
            {"type": "command", "command": capture_command("Stop"), "timeout": 5}
        ],
        "PreToolUse": [
            {
                "matcher": "invoke_subagent",
                "hooks": [
                    {"type": "command", "command": capture_command("SubagentStart"), "timeout": 5}
                ]
            }
        ],
        "PostToolUse": [
            {
                "matcher": "invoke_subagent",
                "hooks": [
                    {"type": "command", "command": capture_command("SubagentStop"), "timeout": 5}
                ]
            }
        ],
    }

    existing["ai-operations-room"] = entry
    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Hooks do Gemini registrados em {path}")


def remove_hooks(path: Path | None = None) -> None:
    path = path or hooks_file_path()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if "ai-operations-room" in data:
        data.pop("ai-operations-room")
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Hooks do Gemini removidos de {path}")
