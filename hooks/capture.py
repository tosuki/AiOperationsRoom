"""Claude Code & Gemini hook: append metadata only, never conversation content."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

FIELDS = ("hook_event_name", "session_id", "cwd", "agent_id", "agent_type", "reason")
BACKGROUND_FIELDS = ("id", "type", "status", "agent_type")


def data_dir() -> Path:
    return Path(os.environ.get("AI_OPERATIONS_ROOM_DATA_DIR")
                or Path.home() / ".ai-operations-room").expanduser()


def _parse_cwd(raw_uris: object) -> str:
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


def normalize(payload: dict, event_override: str | None = None) -> dict:
    if "conversationId" in payload:
        cid = payload["conversationId"]
        cwd = _parse_cwd(payload.get("workspacePaths"))
        raw_event = event_override or payload.get("hook_event_name") or "PreInvocation"

        if raw_event == "PreInvocation":
            event_name = "UserPromptSubmit"
        elif raw_event in ("PreToolUse", "SubagentStart"):
            event_name = "SubagentStart"
        elif raw_event in ("PostToolUse", "SubagentStop"):
            event_name = "SubagentStop"
        elif raw_event == "Stop":
            event_name = "Stop"
        else:
            event_name = raw_event

        event: dict = {
            "id": str(uuid.uuid4()),
            "session_id": cid,
            "evento": event_name,
            "cwd": cwd,
            "t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

        tool_call = payload.get("toolCall")
        if isinstance(tool_call, dict) and tool_call.get("name") == "invoke_subagent":
            args = tool_call.get("args") or {}
            subagents = args.get("Subagents") or []
            if isinstance(subagents, list) and subagents:
                first_sub = subagents[0] if isinstance(subagents[0], dict) else {}
                event["agent_id"] = f"{cid}-sub-{first_sub.get('Role', 'agent')}"
                event["agent_type"] = first_sub.get("Role") or first_sub.get("TypeName") or "subagente"
        elif payload.get("agent_id"):
            event["agent_id"] = payload["agent_id"]
            if payload.get("agent_type"):
                event["agent_type"] = payload["agent_type"]

        return event

    event = {key: payload[key] for key in FIELDS if key in payload}
    event["evento"] = event.pop("hook_event_name", "desconhecido")
    event["id"] = str(uuid.uuid4())
    event["t"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tasks = payload.get("background_tasks")
    if isinstance(tasks, list):
        event["background_tasks"] = [
            {key: task[key] for key in BACKGROUND_FIELDS if key in task}
            for task in tasks if isinstance(task, dict)
        ]
    return event


def main() -> int:
    try:
        raw_input = sys.stdin.read() or "{}"
        payload = json.loads(raw_input)
        if not isinstance(payload, dict):
            return 0

        event_arg = sys.argv[1] if len(sys.argv) > 1 else None

        sid = payload.get("session_id") or payload.get("conversationId")
        if not sid:
            if event_arg:
                sys.stdout.write("{}\n")
            return 0

        path = data_dir()
        path.mkdir(parents=True, exist_ok=True)
        normalized = normalize(payload, event_arg)
        with (path / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(normalized, ensure_ascii=False) + "\n")

        if event_arg in ("PreToolUse", "SubagentStart"):
            sys.stdout.write(json.dumps({"decision": "allow"}) + "\n")
        elif "conversationId" in payload or event_arg:
            sys.stdout.write("{}\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
