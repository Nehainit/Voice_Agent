from __future__ import annotations

import hashlib
import uuid
from collections import deque
from datetime import UTC, datetime
from threading import RLock
from typing import Any

_MAX_TURNS = 10
_LOCK = RLock()
_STATE: dict[str, Any] = {
    "current_topic": "",
    "recent_turns": deque(maxlen=_MAX_TURNS),
    "active_mode": "chat",
    "last_selected_code_summary": "",
    "current_task": None,
}


def get_session_context() -> dict[str, Any]:
    with _LOCK:
        return {
            "current_topic": _STATE["current_topic"],
            "recent_turns": list(_STATE["recent_turns"]),
            "active_mode": _STATE["active_mode"],
            "last_selected_code_summary": _STATE["last_selected_code_summary"],
            "current_task": _clone_task(_STATE["current_task"]),
        }


def render_session_context(context: dict[str, Any] | None = None) -> str:
    data = context or get_session_context()
    lines: list[str] = []
    topic = str(data.get("current_topic") or "").strip()
    if topic:
        lines.append(f"Current topic: {topic}")
    mode = str(data.get("active_mode") or "").strip()
    if mode:
        lines.append(f"Active mode: {mode}")
    code_summary = str(data.get("last_selected_code_summary") or "").strip()
    if code_summary:
        lines.append(f"Code context: {code_summary}")
    task = data.get("current_task") or {}
    if task:
        lines.append(
            "Current task: "
            f"{task.get('title') or task.get('problemStatement') or 'Untitled'} "
            f"({task.get('status') or 'TASK_ACTIVE'})"
        )
        waiting_for = str(task.get("waitingFor") or "").strip()
        if waiting_for:
            lines.append(f"Waiting for: {waiting_for}")
    turns = list(data.get("recent_turns") or [])[-6:]
    if turns:
        lines.append("Recent turns:")
        for turn in turns:
            user = _compact(turn.get("user", ""), 180)
            assistant = _compact(turn.get("assistant", ""), 180)
            if user:
                lines.append(f"- User: {user}")
            if assistant:
                lines.append(f"  Neha: {assistant}")
    return "\n".join(lines).strip()


def update_session_context(
    *,
    user_text: str,
    assistant_text: str,
    intent: str,
    ui_state: str,
    selected_text: str = "",
) -> None:
    user = _compact(user_text, 400)
    assistant = _compact(assistant_text, 400)
    if not user and not assistant:
        return

    with _LOCK:
        _STATE["active_mode"] = _mode_for(intent, ui_state)
        topic = _derive_topic(user, intent, selected_text)
        if topic:
            _STATE["current_topic"] = topic
        if selected_text.strip():
            _STATE["last_selected_code_summary"] = _summarize_selected_code(selected_text)
        _STATE["recent_turns"].append(
            {
                "user": user,
                "assistant": assistant,
                "intent": intent or "unknown",
                "ui_state": ui_state or "answer",
            }
        )


def update_task_memory(
    *,
    user_text: str,
    assistant_text: str,
    intent: str,
    ui_state: str,
    selected_text: str = "",
    context: dict[str, Any] | None = None,
    agent_id: str = "general_assistant",
) -> dict[str, Any] | None:
    context = context or {}
    now = _now()
    user = _compact(user_text, 700)
    assistant = _compact(assistant_text, 700)

    with _LOCK:
        current = _clone_task(_STATE["current_task"])

        if _is_resolution_confirmation(user) and current:
            current["status"] = "RESOLVED"
            current["resolvedAt"] = now
            current["updatedAt"] = now
            current.setdefault("evidence", []).append({"type": "user_confirmation", "text": user, "at": now})
            _STATE["current_task"] = current
            return _clone_task(current)

        if agent_id != "code_assistant":
            return _clone_task(current)

        should_create = intent in {"explain", "debug", "review", "fix", "refactor", "replace", "write_test"} and (
            bool(selected_text.strip()) or not current
        )
        should_continue = current and (
            _is_continuation(user)
            or intent in {"chat", "debug", "fix", "review", "explain"}
            or ui_state in {"answer", "patch_preview", "needs_project_root"}
        )

        if not should_create and not should_continue:
            return _clone_task(current)

        task = current if current and current.get("status") != "RESOLVED" else None
        if task is None:
            task = {
                "taskId": f"task_{uuid.uuid4().hex[:12]}",
                "agentId": agent_id,
                "status": "TASK_ACTIVE",
                "intent": intent or "unknown",
                "title": _task_title(user, intent),
                "problemStatement": user,
                "selectedCodeSummary": "",
                "selectedCodeHash": "",
                "fileName": "",
                "filePath": "",
                "projectRoot": "",
                "attempts": [],
                "lastAssistantStep": "",
                "waitingFor": "",
                "evidence": [],
                "createdAt": now,
                "updatedAt": now,
                "resolvedAt": None,
            }

        task["agentId"] = agent_id
        task["intent"] = intent or task.get("intent") or "unknown"
        task["updatedAt"] = now
        task["fileName"] = str(context.get("fileName") or task.get("fileName") or "")
        task["filePath"] = str(context.get("filePath") or task.get("filePath") or "")
        task["projectRoot"] = str(context.get("projectRoot") or task.get("projectRoot") or "")
        if user and not task.get("problemStatement"):
            task["problemStatement"] = user
        if selected_text.strip():
            task["selectedCodeSummary"] = _summarize_selected_code(selected_text)
            task["selectedCodeHash"] = hashlib.sha256(selected_text.encode("utf-8")).hexdigest()[:16]

        if assistant:
            task["lastAssistantStep"] = _next_step_from_answer(assistant)
            task["waitingFor"] = _waiting_for(task["lastAssistantStep"], ui_state)
            if ui_state in {"answer", "patch_preview", "needs_project_root"}:
                task["status"] = "WAITING_FOR_USER_RESULT"
            task.setdefault("attempts", []).append(
                {
                    "intent": intent or "unknown",
                    "uiState": ui_state or "answer",
                    "user": user,
                    "assistant": assistant,
                    "at": now,
                }
            )
            task["attempts"] = task["attempts"][-8:]

        _STATE["current_task"] = task
        return _clone_task(task)


def get_current_task() -> dict[str, Any] | None:
    with _LOCK:
        return _clone_task(_STATE["current_task"])


def clear_session_context() -> None:
    with _LOCK:
        _STATE["current_topic"] = ""
        _STATE["recent_turns"].clear()
        _STATE["active_mode"] = "chat"
        _STATE["last_selected_code_summary"] = ""
        _STATE["current_task"] = None


def _is_resolution_confirmation(text: str) -> bool:
    normalized = str(text or "").lower()
    return any(
        phrase in normalized
        for phrase in (
            "fixed",
            "done",
            "solved",
            "working",
            "it works",
            "chal gaya",
            "ho gaya",
            "ho gya",
            "sahi ho gaya",
            "tests passed",
        )
    )


def _is_continuation(text: str) -> bool:
    normalized = str(text or "").lower()
    return any(
        phrase in normalized
        for phrase in (
            "same error",
            "still not working",
            "still failing",
            "ab kya",
            "now what",
            "next",
            "traceback",
            "error again",
            "not fixed",
            "same issue",
        )
    )


def _task_title(user_text: str, intent: str) -> str:
    if intent:
        label = intent.replace("_", " ").title()
    else:
        label = "Code Task"
    compact = _compact(user_text, 80)
    return f"{label}: {compact}" if compact else label


def _next_step_from_answer(answer: str) -> str:
    sentences = [item.strip() for item in str(answer or "").split(".") if item.strip()]
    if not sentences:
        return ""
    return sentences[-1][:220]


def _waiting_for(last_step: str, ui_state: str) -> str:
    if ui_state == "patch_preview":
        return "User approval or modification request for the patch preview."
    if ui_state == "needs_project_root":
        return "User confirmation of the project root or selected-only mode."
    if last_step:
        return "User result after trying the suggested next step."
    return ""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _clone_task(task: dict[str, Any] | None) -> dict[str, Any] | None:
    if not task:
        return None
    return {
        **task,
        "attempts": list(task.get("attempts") or []),
        "evidence": list(task.get("evidence") or []),
    }


def _derive_topic(user_text: str, intent: str, selected_text: str) -> str:
    text = user_text.lower()
    if any(word in text for word in ("interrupt", "interruption", "stop talking", "not listening", "human", "barge")):
        return "Making Neha interruptible and more human-like during voice conversation"
    if any(word in text for word in ("context", "topic", "remember what", "overall")):
        return "Maintaining session context across the current conversation"
    if any(word in text for word in ("memory", "persist", "postgres", "database")):
        return "Persistent memory architecture for the voice agent"
    if any(word in text for word in ("frontend", "particle", "sphere", "animation", "music", "bubble")):
        return "Designing the Neha desktop frontend experience"
    if selected_text.strip() or intent in {"explain", "debug", "review", "fix", "refactor", "replace", "write_test"}:
        return "Working with the currently selected code"
    return ""


def _mode_for(intent: str, ui_state: str) -> str:
    if ui_state in {"patch_preview", "needs_project_root"}:
        return "code_edit"
    if intent in {"explain", "debug", "review"}:
        return "code_answer"
    if intent in {"fix", "refactor", "replace", "write_test"}:
        return "code_edit"
    return "chat"


def _summarize_selected_code(selected_text: str) -> str:
    lines = [line.strip() for line in selected_text.splitlines() if line.strip()]
    if not lines:
        return ""
    first = _compact(lines[0], 120)
    return f"{len(lines)} selected line(s), starting with: {first}"


def _compact(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "..."
