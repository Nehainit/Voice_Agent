from __future__ import annotations

import ast
import json
import logging
import re
import time
import asyncio
from pathlib import Path
from typing import Any, Literal, TypedDict

from .llm import ask_ollama
from .session_state import render_session_context


LOGGER = logging.getLogger(__name__)

ContextKind = Literal["none", "file", "selection"]
Route = Literal["answer", "patch", "clarify"]
ProjectContextStatus = Literal["ready", "needs_project_root", "selected_only", "invalid"]
Intent = Literal[
    "chat",
    "explain",
    "debug",
    "review",
    "fix",
    "refactor",
    "replace",
    "write_test",
    "clarify",
    "unknown",
]


class AgentState(TypedDict, total=False):
    mode: str
    transcript: str
    command_text: str
    context: dict[str, Any]
    context_kind: ContextKind
    language_id: str
    file_name: str
    file_path: str
    project_root: str
    project_root_approved: bool
    selected_only: bool
    window_title: str
    selected_text: str
    surrounding_text: str
    selected_range: str
    has_selection: bool
    intent: Intent
    route: Route
    confidence: float
    needs_clarification: bool
    clarifying_question: str
    answer: str
    proposed_code: str
    patch_title: str
    patch_feedback: str
    patch_iterations: int
    project_context_status: ProjectContextStatus
    project_context_message: str
    project_context_required: bool
    diff: str
    allow_test_run: bool
    test_command: list[str]
    test_iterations: int
    working_directory: str
    test_status: Literal["skipped", "passed", "failed", "error"]
    test_exit_code: int | None
    test_output: str
    test_duration_seconds: float
    approval: Literal["pending", "approved", "cancelled", "modify"]
    warnings: list[str]
    session_context: dict[str, Any]
    agent_id: str
    agent_name: str
    response_language: str
    keep_technical_terms_english: bool


def input_node(state: AgentState) -> AgentState:
    """Normalize raw request data into the graph state.

    Expected input:
    - transcript: text produced by STT, or
    - command_text: typed fallback / follow-up text
    - context: VS Code editor context sent by the extension
    """
    context = state.get("context") or {}
    selected_text = _clean(context.get("selectedText"))
    surrounding_text = _clean(context.get("surroundingText"))
    command_text = _clean(state.get("transcript")) or _clean(state.get("command_text"))
    warnings = list(state.get("warnings") or [])

    if not command_text:
        warnings.append("No voice command or text command was provided.")

    context_kind: ContextKind = "none"
    if selected_text:
        context_kind = "selection"
    elif surrounding_text or context.get("fileName"):
        context_kind = "file"

    return {
        **state,
        "mode": _clean(state.get("mode")) or "debug",
        "transcript": _clean(state.get("transcript")),
        "command_text": command_text,
        "context": context,
        "context_kind": context_kind,
        "language_id": _clean(context.get("languageId")) or "unknown",
        "file_name": _clean(context.get("fileName")) or "unknown",
        "file_path": _clean(context.get("filePath")),
        "project_root": _clean(context.get("projectRoot")),
        "project_root_approved": bool(context.get("projectRootApproved", False)),
        "selected_only": bool(context.get("selectedOnly", False)),
        "window_title": _clean(context.get("windowTitle")),
        "selected_text": selected_text,
        "surrounding_text": surrounding_text,
        "selected_range": _clean(context.get("selectedRange")),
        "has_selection": bool(selected_text),
        "allow_test_run": bool(state.get("allow_test_run", False)),
        "test_command": list(state.get("test_command") or []),
        "test_iterations": int(state.get("test_iterations") or 1),
        "working_directory": _clean(state.get("working_directory")),
        "patch_iterations": int(state.get("patch_iterations") or 1),
        "approval": state.get("approval") or "pending",
        "warnings": warnings,
        "session_context": dict(state.get("session_context") or {}),
        "agent_id": _clean(state.get("agent_id")) or "general_assistant",
        "agent_name": _clean(state.get("agent_name")) or "Neha",
        "response_language": _clean(state.get("response_language")) or "English",
        "keep_technical_terms_english": bool(state.get("keep_technical_terms_english", True)),
    }


def project_context_gate_node(state: AgentState) -> AgentState:
    route = route_after_intent(state)
    warnings = list(state.get("warnings") or [])

    if route != "patch":
        return {
            **state,
            "project_context_status": "ready",
            "project_context_required": False,
            "project_context_message": "",
            "warnings": warnings,
        }

    if state.get("selected_only"):
        warnings.append("Continuing with selected-code-only patch context.")
        return {
            **state,
            "project_context_status": "selected_only",
            "project_context_required": False,
            "project_context_message": "Continuing with selected code only.",
            "warnings": warnings,
        }

    project_root = _clean(state.get("project_root"))
    if not project_root:
        return {
            **state,
            "project_context_status": "needs_project_root",
            "project_context_required": True,
            "project_context_message": "Choose the project folder so I can inspect related files before proposing a safer fix.",
            "warnings": warnings,
        }

    validation_error = validate_project_root(project_root)
    if validation_error:
        return {
            **state,
            "project_context_status": "invalid",
            "project_context_required": True,
            "project_context_message": validation_error,
            "warnings": warnings,
        }

    if not state.get("project_root_approved"):
        return {
            **state,
            "project_context_status": "needs_project_root",
            "project_context_required": True,
            "project_context_message": "Please confirm this project folder before I inspect related files.",
            "warnings": warnings,
        }

    file_path_error = validate_file_path_inside_project(_clean(state.get("file_path")), project_root)
    if file_path_error:
        warnings.append(file_path_error)

    return {
        **state,
        "project_context_status": "ready",
        "project_context_required": False,
        "project_context_message": "Project folder approved.",
        "warnings": warnings,
    }


def classify_intent_node(state: AgentState) -> AgentState:
    command = _clean(state.get("command_text")).lower()
    warnings = list(state.get("warnings") or [])

    if not command:
        return {
            **state,
            "intent": "clarify",
            "route": "clarify",
            "confidence": 1.0,
            "needs_clarification": True,
            "clarifying_question": "What would you like me to do with the selected code?",
        }

    intent: Intent = "unknown"
    confidence = 0.2

    if is_vague_code_fragment(command):
        return {
            **state,
            "intent": "clarify",
            "route": "clarify",
            "confidence": 0.92,
            "needs_clarification": True,
            "clarifying_question": "What should I do with the selected code: explain, review, debug, or change it?",
            "warnings": warnings,
        }

    if _contains_any(command, "test", "unit test", "spec"):
        intent = "write_test"
        confidence = 0.9
    elif _contains_any(command, "refactor", "clean up", "cleanup", "simplify", "better", "improve", "optimize", "production ready", "clean"):
        intent = "refactor"
        confidence = 0.9
    elif _contains_any(command, "replace", "change", "convert", "rewrite"):
        intent = "replace"
        confidence = 0.85
    elif _contains_any(command, "review", "risk", "edge case", "issue", "problems", "sahi hai", "theek hai", "looks ok", "is this correct"):
        intent = "review"
        confidence = 0.85
    elif _contains_any(command, "fix", "repair", "solve", "correct this", "sahi kar", "theek kar"):
        intent = "fix"
        confidence = 0.9
    elif _contains_any(command, "debug", "bug", "error", "fail", "failing", "why"):
        intent = "debug"
        confidence = 0.85
    elif is_conversational_command(command):
        intent = "chat"
        confidence = 0.95
    elif _contains_any(command, "explain", "what", "describe", "samjha", "bata"):
        intent = "explain"
        confidence = 0.9

    route = route_for_intent(intent)
    return {
        **state,
        "intent": intent,
        "route": route,
        "confidence": confidence,
        "needs_clarification": route == "clarify",
        "clarifying_question": default_clarifying_question(intent),
        "warnings": warnings,
    }


async def llm_orchestrator_node(state: AgentState, model: str | None = None, num_ctx: int | None = None) -> AgentState:
    if state.get("confidence", 0.0) >= 0.75:
        return state

    prompt = build_orchestrator_prompt(state)
    warnings = list(state.get("warnings") or [])

    try:
        raw_response = await ask_ollama(prompt, model=model, num_ctx=num_ctx)
    except Exception as error:
        warnings.append(f"LLM orchestrator unavailable; used deterministic route: {error}")
        return deterministic_orchestrator_fallback(state, warnings)

    try:
        parsed = parse_orchestrator_response(raw_response)
    except Exception as error:
        LOGGER.warning("LLM orchestrator parse failed: %s", _safe_log_snippet(raw_response))
        warnings.append(f"LLM orchestrator parse failed; used deterministic route: {error}")
        return deterministic_orchestrator_fallback(state, warnings)

    intent = normalize_intent(parsed.get("intent"))
    route = normalize_route(parsed.get("route")) or route_for_intent(intent)
    confidence = clamp_float(parsed.get("confidence"), default=0.5)
    needs_clarification = bool(parsed.get("needsClarification", route == "clarify"))
    clarifying_question = _clean(parsed.get("clarifyingQuestion")) or default_clarifying_question(intent)

    if confidence < 0.55:
        intent = "clarify"
        route = "clarify"
        needs_clarification = True

    return {
        **state,
        "intent": intent,
        "route": route,
        "confidence": confidence,
        "needs_clarification": needs_clarification,
        "clarifying_question": clarifying_question,
        "warnings": warnings,
    }


def deterministic_orchestrator_fallback(state: AgentState, warnings: list[str]) -> AgentState:
    fallback_intent = state.get("intent", "unknown")
    fallback_route = route_for_intent(fallback_intent)
    return {
        **state,
        "intent": fallback_intent,
        "route": fallback_route,
        "confidence": state.get("confidence", 0.0),
        "needs_clarification": fallback_route == "clarify",
        "clarifying_question": default_clarifying_question(fallback_intent),
        "warnings": warnings,
    }


async def answer_node(state: AgentState, model: str | None = None, num_ctx: int | None = None) -> AgentState:
    warnings = list(state.get("warnings") or [])
    if state.get("intent") == "chat":
        return {
            **state,
            "answer": conversational_answer(
                _clean(state.get("command_text")),
                state.get("session_context"),
                _clean(state.get("response_language")),
            ),
            "warnings": warnings,
        }

    prompt = build_answer_prompt(state)

    try:
        answer = await ask_ollama(prompt, model=model, num_ctx=num_ctx)
    except Exception as error:
        warnings.append(f"Answer generation failed: {error}")
        answer = fallback_answer(state)

    return {
        **state,
        "answer": shape_spoken_answer(answer, state),
        "warnings": warnings,
    }


async def patch_node(state: AgentState, model: str | None = None, num_ctx: int | None = None) -> AgentState:
    warnings = list(state.get("warnings") or [])
    selected_text = _clean(state.get("selected_text"))

    if not selected_text:
        return {
            **state,
            "answer": "Please highlight the code first, then ask again.",
            "proposed_code": "",
            "patch_title": "No selected code",
            "warnings": warnings,
        }

    max_iterations = max(1, min(int(state.get("patch_iterations") or 1), 5))
    proposed_code = ""
    feedback = _clean(state.get("patch_feedback"))

    for attempt in range(1, max_iterations + 1):
        prompt = build_patch_prompt(state, feedback=feedback, attempt=attempt, max_attempts=max_iterations)
        try:
            raw_response = await ask_ollama(prompt, model=model, num_ctx=num_ctx)
            proposed_code = extract_code_from_model_response(raw_response)
        except Exception as error:
            warnings.append(f"Patch generation failed: {error}")
            proposed_code = fallback_patch(state)
            feedback = ""
            break

        validation_error = validate_proposed_code(selected_text, proposed_code)
        if not validation_error:
            feedback = ""
            break
        feedback = validation_error
        warnings.append(f"Patch attempt {attempt} needed revision: {validation_error}")

    if not proposed_code:
        proposed_code = fallback_patch(state)

    return {
        **state,
        "answer": patch_answer(state, max_iterations),
        "proposed_code": proposed_code,
        "patch_title": patch_title(state),
        "patch_feedback": feedback,
        "patch_iterations": max_iterations,
        "warnings": warnings,
    }


async def run_tests_node(state: AgentState, timeout_seconds: int = 120) -> AgentState:
    warnings = list(state.get("warnings") or [])
    command = list(state.get("test_command") or [])
    working_directory = _clean(state.get("working_directory"))
    test_iterations = max(1, min(int(state.get("test_iterations") or 1), 5))

    if not state.get("allow_test_run"):
        return {
            **state,
            "test_status": "skipped",
            "test_output": "Test run skipped because allowTestRun was false.",
            "test_exit_code": None,
            "test_duration_seconds": 0.0,
            "test_iterations": test_iterations,
            "warnings": warnings,
        }

    if not command:
        return {
            **state,
            "test_status": "skipped",
            "test_output": "Test run skipped because no test command was provided.",
            "test_exit_code": None,
            "test_duration_seconds": 0.0,
            "test_iterations": test_iterations,
            "warnings": warnings,
        }

    if not is_allowed_test_command(command):
        warnings.append("Test command was rejected by the backend allowlist.")
        return {
            **state,
            "test_status": "error",
            "test_output": f"Rejected test command: {' '.join(command)}",
            "test_exit_code": None,
            "test_duration_seconds": 0.0,
            "test_iterations": test_iterations,
            "warnings": warnings,
        }

    cwd = Path(working_directory or ".").expanduser().resolve()
    if not cwd.exists() or not cwd.is_dir():
        warnings.append("Test working directory does not exist.")
        return {
            **state,
            "test_status": "error",
            "test_output": f"Invalid working directory: {cwd}",
            "test_exit_code": None,
            "test_duration_seconds": 0.0,
            "test_iterations": test_iterations,
            "warnings": warnings,
        }

    started_at = time.monotonic()
    output_parts: list[str] = []
    exit_code: int | None = None
    for iteration in range(1, test_iterations + 1):
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                output_bytes, _ = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                warnings.append(f"Test command timed out on iteration {iteration}.")
                return {
                    **state,
                    "test_status": "error",
                    "test_output": f"Test command timed out after {timeout_seconds} seconds on iteration {iteration}.",
                    "test_exit_code": None,
                    "test_duration_seconds": round(time.monotonic() - started_at, 3),
                    "test_iterations": test_iterations,
                    "warnings": warnings,
                }
        except OSError as error:
            warnings.append(f"Test command failed to start: {error}")
            return {
                **state,
                "test_status": "error",
                "test_output": str(error),
                "test_exit_code": None,
                "test_duration_seconds": round(time.monotonic() - started_at, 3),
                "test_iterations": test_iterations,
                "warnings": warnings,
            }

        exit_code = process.returncode
        output = output_bytes.decode("utf-8", errors="replace")
        output_parts.append(f"--- Test iteration {iteration}/{test_iterations} ---\n{output}")
        if exit_code != 0:
            break

    combined_output = "\n".join(output_parts)
    return {
        **state,
        "test_status": "passed" if exit_code == 0 else "failed",
        "test_output": combined_output[-12000:],
        "test_exit_code": exit_code,
        "test_duration_seconds": round(time.monotonic() - started_at, 3),
        "test_iterations": test_iterations,
        "warnings": warnings,
    }


def route_after_intent(state: AgentState) -> Literal["answer", "patch", "clarify"]:
    return state.get("route") or route_for_intent(state.get("intent", "unknown"))


def route_for_intent(intent: str) -> Route:
    if intent in ("chat", "explain", "debug", "review"):
        return "answer"
    if intent in ("fix", "refactor", "replace", "write_test"):
        return "patch"
    return "clarify"


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    phrase = phrase.strip().lower()
    if not phrase:
        return False
    if " " in phrase:
        return phrase in text
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def _contains_any(text: str, *needles: str) -> bool:
    return any(_contains_phrase(text, needle) for needle in needles)


def is_vague_code_fragment(command: str) -> bool:
    command = command.strip().lower()
    if not command:
        return False
    code_markers = ("selected code", "this code", "class", "function", "method", "component", "file", "line")
    action_markers = (
        "explain", "what", "why", "how", "review", "debug", "fix", "change", "replace",
        "refactor", "test", "write", "create", "tell", "describe", "check", "issue", "problem",
    )
    starts_like_fragment = command.startswith(("of ", "for ", "this ", "selected ", "particular "))
    has_code_marker = any(marker in command for marker in code_markers)
    has_action = any(marker in command for marker in action_markers)
    return has_code_marker and (starts_like_fragment or not has_action)


def is_conversational_command(command: str) -> bool:
    command = command.strip().lower()
    if not command:
        return False

    conversational_phrases = (
        "how do i pronounce your name",
        "how to pronounce your name",
        "pronounce your name",
        "what is your name",
        "who are you",
        "what are we talking",
        "what are we talking about",
        "what is the topic",
        "current topic",
        "overall context",
        "can you talk",
        "do you talk",
        "do you only talk about code",
        "so you don't talk apart from code",
        "so you dont talk apart from code",
        "thank you",
        "thanks",
        "hello",
        "hi",
        "hey",
        "are you there",
        "how do you work",
        "how do you actually work",
        "tell me how do you work",
        "tell me how you work",
        "how do you function",
        "listen like a human",
        "stop speaking when interrupted",
        "when interrupted",
        "barge in",
        "barge-in",
        "what exactly are you",
        "what exactly do you want",
        "i understand",
        "i understood",
        "i get it",
        "got it",
        "makes sense",
        "that makes sense",
        "samajh gaya",
        "samajh gayi",
        "are you neha",
        "are you codeduck",
        "code dog",
        "coding partner",
        "we don't need your help",
        "we dont need your help",
        "i don't need your help",
        "i dont need your help",
        "don't need your help",
        "dont need your help",
        "no need",
        "not now",
        "go away",
        "no thanks",
    )
    if "neha" in command and any(phrase in command for phrase in ("improve", "improving", "listen", "speaking", "interrupt", "human", "conversation", "context")):
        return True
    if any(_contains_phrase(command, phrase) for phrase in conversational_phrases):
        return True

    coding_markers = (
        "code", "file", "function", "bug", "error", "fix", "debug", "review",
        "refactor", "test", "api", "component", "class", "method", "variable",
    )
    if any(_contains_phrase(command, marker) for marker in coding_markers):
        return False

    social_starters = ("hi", "hello", "hey", "thanks", "thank you")
    return command in social_starters


def build_orchestrator_prompt(state: AgentState) -> str:
    selected_text = _clean(state.get("selected_text"))
    code_preview = selected_text[:1800]
    return f"""You are the routing orchestrator for a desktop AI companion platform.

Classify the user's command. Do not answer the user and do not rewrite code.

Return only valid JSON with this exact shape:
{{
  "intent": "chat|explain|debug|review|fix|refactor|replace|write_test|clarify|unknown",
  "route": "answer|patch|clarify",
  "confidence": 0.0,
  "needsClarification": false,
  "clarifyingQuestion": ""
}}

Strict output rules:
- Return exactly one JSON object.
- Use double quotes for every key and string.
- Do not wrap the JSON in markdown fences.
- Do not add prose before or after the JSON.
- Do not omit commas between fields.
- If unsure, return intent "unknown", route "clarify", and a short clarifyingQuestion.

Routing rules:
- answer: chat, explain, debug, review, or questions asking whether code is correct.
- chat: casual conversation, identity/name questions, thanks, or meta questions about whether you can talk beyond code.
- patch: fix, refactor, replace, improve, optimize, clean up, convert, or write tests.
- clarify: vague coding commands like "do it" without enough intent.
- Understand Hinglish and casual developer language.
- Human-like behavior comes from task memory and follow-through, not always-on mic.
- Do not ask the frontend to listen again.

Active agent: {_clean(state.get("agent_name")) or "Neha"} ({_clean(state.get("agent_id")) or "general_assistant"})
Preferred response language: {_clean(state.get("response_language")) or "English"}

User command:
{_clean(state.get("command_text"))}

Session context:
{render_session_context(state.get("session_context")) or "No prior session context."}

File: {_clean(state.get("file_name")) or "unknown"}
Language: {_clean(state.get("language_id")) or "unknown"}

Selected code preview:
```{_clean(state.get("language_id")) or "text"}
{code_preview}
```
"""


def conversational_answer(command: str, session_context: dict[str, Any] | None = None, response_language: str = "English") -> str:
    text = command.strip().lower()
    topic = str((session_context or {}).get("current_topic") or "").strip()
    hinglish = str(response_language or "").lower() == "hinglish"
    if not text:
        return "Mujhe clearly catch nahi hua." if hinglish else "I did not catch that clearly."
    if any(phrase in text for phrase in ("what are we talking", "what is the topic", "what context", "overall context", "current topic")):
        if topic:
            return f"Haan, current topic hai: {topic}." if hinglish else f"Current topic: {topic}."
        return "Abhi ek fixed topic set nahi hua." if hinglish else "We have not settled on one topic yet."
    if "neha" in text and any(phrase in text for phrase in ("improve", "improving", "interrupt", "listen like a human", "human")):
        return "Haan, hum Neha ko more human-like bana rahe hain, but mic always-on nahi rakhenge." if hinglish else "Got it. We are improving Neha's human-like behavior without always-on listening."
    if "pronounce" in text and "name" in text:
        return "Mera naam Neha hai. Pronounce it Nay-ha." if hinglish else "My name is Neha. Pronounce it Nay-ha."
    if "how" in text and "work" in text:
        return "Main shortcut ya mic press ke baad hi sunti hoon, speech ko text banati hoon, phir selected context ke saath answer deti hoon." if hinglish else "I listen only after you trigger me, transcribe your speech, then answer or help with selected context."
    if "code dog" in text or "codeduck" in text or "are you neha" in text:
        return "Main Neha hoon. CodeDuck sirf internal app name hai." if hinglish else "I am Neha. CodeDuck is only the internal app name."
    if "what exactly" in text and "want" in text:
        return "Kuch nahi. Main wait karti hoon, ask karoge toh answer dungi, aur stop bolne par quiet rahungi." if hinglish else "Nothing from you. I wait, answer when asked, and stay quiet when told."
    if ("only" in text and "code" in text) or "apart from code" in text:
        return "Haan, normal baat bhi kar sakti hoon, bas concise rahungi." if hinglish else "I can talk normally too, but I will keep it brief."
    if any(phrase in text for phrase in ("don't need your help", "dont need your help", "no need", "not now", "go away", "no thanks")):
        return "Theek hai, main quiet rahungi." if hinglish else "Okay, I will stay quiet."
    if text in {"thank you", "thanks", "thank you.", "okay thanks", "ok thanks"}:
        return "Welcome." if hinglish else "You are welcome."
    if "how are you" in text or "how r you" in text:
        return "Main theek hoon. Tum jab mic press karoge ya code point karoge, main help kar dungi." if hinglish else "I’m good. I’m here with you, and ready when you want to talk or point me at some code."
    if text in {"hi", "hello", "hey"}:
        return "Hi, main yahin hoon." if hinglish else "Hi. I’m here with you."
    if len(text.split()) <= 3:
        return "Maine suna, bas thoda aur detail chahiye." if hinglish else "I heard you, but I need a little more detail."
    return "Maine suna. Batao exactly kya karna hai ya kya puchna hai." if hinglish else "I heard you. Please say exactly what you want me to do or ask."


def build_answer_prompt(state: AgentState) -> str:
    intent = state.get("intent", "unknown")
    selected_text = _clean(state.get("selected_text"))
    surrounding_text = _clean(state.get("surrounding_text"))
    code_context = selected_text or surrounding_text or "No selected code was provided."
    session_context_text = render_session_context(state.get("session_context")) or "No prior session context."
    language = _clean(state.get("language_id")) or "unknown"
    file_name = _clean(state.get("file_name")) or "unknown"
    selected_range = _clean(state.get("selected_range")) or "unknown"
    instruction = answer_instruction(intent)
    agent_name = _clean(state.get("agent_name")) or "Neha"
    response_language = _clean(state.get("response_language")) or "English"
    keep_terms = "yes" if state.get("keep_technical_terms_english", True) else "no"
    task = (state.get("session_context") or {}).get("current_task") or {}
    current_task = task.get("title") or task.get("problemStatement") or "No active task."

    return f"""You are {agent_name}, a friendly desktop AI companion talking by voice.

Rules:
- You are part of a multi-agent desktop platform with named agents.
- Human-like behavior comes from memory, routing, and follow-through, not always-on mic.
- Do not say "I am listening" unless the mic is actually recording.
- Respond in {response_language}. If Hinglish, use natural Hinglish and keep technical terms in English.
- Keep technical terms in English: {keep_terms}.
- If selected code is provided, answer the user's question about that code.
- If no selected code is provided, answer as a normal short conversation.
- Do not rewrite or replace the code in this response.
- Do not return a patch or diff.
- If a code change seems needed, describe the issue and say a replacement can be proposed separately.
- Sound like a human coding partner, not documentation, slides, or a lecture.
- Keep the answer short enough to speak comfortably: usually 1-3 sentences.
- Use simple conversational wording.
- Do not use headings, markdown tables, long bullet lists, or step-by-step lecture format.
- If the user asks "what does this line do", explain that line directly in one sentence.
- If the user sounds unsure, answer gently and add only the most useful next hint.
- Give one next useful step when it helps.
- If a side question is related to the active task, answer briefly and return to the task.
- Do not invent files, test results, APIs, or runtime behavior not shown in the context.

Intent: {intent}
Instruction: {instruction}
Active task: {current_task}

Session context:
{session_context_text}

File: {file_name}
Selected range: {selected_range}
Language: {language}

User command:
{_clean(state.get("command_text"))}

Selected code:
```{language}
{code_context}
```

Answer:"""


def build_patch_prompt(state: AgentState, feedback: str, attempt: int, max_attempts: int) -> str:
    intent = state.get("intent", "fix")
    language = _clean(state.get("language_id")) or "text"
    file_name = _clean(state.get("file_name")) or "unknown"
    file_path = _clean(state.get("file_path")) or "unknown"
    project_root = _clean(state.get("project_root")) or "not provided"
    project_context_status = _clean(state.get("project_context_status")) or "unknown"
    selected_range = _clean(state.get("selected_range")) or "unknown"

    feedback_block = ""
    if feedback:
        feedback_block = f"""
Previous attempt feedback:
{feedback}
Revise the replacement to address this feedback.
"""

    agent_name = _clean(state.get("agent_name")) or "Neha"

    return f"""You are {agent_name}, a senior engineer generating a safe replacement for selected code.

Task:
- Generate replacement code for the selected code only.
- Intent: {intent}
- User command: {_clean(state.get("command_text"))}
- Attempt: {attempt} of {max_attempts}

Rules:
- Return only the replacement code.
- Do not include markdown fences.
- Do not include explanations before or after the code.
- Preserve public function/class names and signatures unless the user explicitly asks to change them.
- Keep the replacement scoped to the selected code.
- Do not claim tests were run.
- If the user asks to write tests, return test code only.
{feedback_block}
File: {file_name}
File path: {file_path}
Project root: {project_root}
Project context mode: {project_context_status}
Selected range: {selected_range}
Language: {language}

Selected code:
```{language}
{_clean(state.get("selected_text"))}
```

Replacement code:"""


def extract_code_from_model_response(response: str) -> str:
    text = response.strip()
    fenced = re.search(r"```(?:[\w.+-]+)?\n(.*?)```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    return text.strip()


def validate_proposed_code(original_code: str, proposed_code: str) -> str:
    if not proposed_code.strip():
        return "The model returned empty replacement code."
    if proposed_code.strip() == original_code.strip():
        return "The replacement is identical to the selected code."
    if "```" in proposed_code:
        return "The replacement still contains markdown fences."
    lowered = proposed_code.lower()
    if lowered.startswith(("here is", "sure,", "explanation", "this code")):
        return "The replacement contains prose instead of code only."
    return ""


def fallback_patch(state: AgentState) -> str:
    selected_text = _clean(state.get("selected_text"))
    return selected_text


def patch_answer(state: AgentState, iterations: int) -> str:
    if state.get("allow_test_run"):
        return f"I prepared a replacement preview after {iterations} generation attempt(s). Tests must run only in an approved workspace/apply flow."
    return f"I prepared a replacement preview after {iterations} generation attempt(s). Review the diff before applying it."


def patch_title(state: AgentState) -> str:
    intent = state.get("intent", "fix")
    if intent == "refactor":
        return "Refactor selected code"
    if intent == "replace":
        return "Replace selected code"
    if intent == "write_test":
        return "Add test code"
    return "Fix selected code"


def answer_instruction(intent: str) -> str:
    if intent == "chat":
        return "Answer conversationally without asking for code or a task."
    if intent == "explain":
        return "Explain the selected code in a short spoken answer. Prefer the core idea over detailed flow."
    if intent == "debug":
        return "Name the likely issue and one concrete check. Do not claim you ran the code."
    if intent == "review":
        return "Mention the most important bug or risk first. Keep it short unless the user asks for detail."
    return "Answer the user's question about the selected code in a short conversational way."


def shape_spoken_answer(answer: str, state: AgentState) -> str:
    text = _clean(answer)
    if not text:
        return text

    lines = []
    for line in text.splitlines():
        clean_line = line.strip()
        if not clean_line:
            continue
        if clean_line.endswith(":") and len(clean_line.split()) <= 5:
            continue
        clean_line = re.sub(r"^[-*•]\s+", "", clean_line)
        clean_line = re.sub(r"^\d+[.)]\s+", "", clean_line)
        lines.append(clean_line)

    text = " ".join(lines)
    text = re.sub(r"\s+", " ", text).strip()

    if state.get("intent") in {"debug", "review"}:
        max_sentences = 3
    else:
        max_sentences = 2

    sentences = re.split(r"(?<=[.!?])\s+", text)
    shaped = " ".join(sentence for sentence in sentences[:max_sentences] if sentence).strip()
    if not shaped:
        shaped = text

    max_chars = 420 if state.get("intent") in {"debug", "review"} else 280
    if len(shaped) > max_chars:
        shaped = shaped[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:") + "."

    return shaped


def fallback_answer(state: AgentState) -> str:
    intent = state.get("intent", "unknown")
    selected_text = _clean(state.get("selected_text"))
    line_count = len(selected_text.splitlines()) if selected_text else 0
    if not selected_text:
        return "I can answer that, but Ollama is unavailable right now. Highlight code when you want code-specific help."
    if intent == "explain":
        return f"I received {line_count} selected line(s). Ollama is unavailable, so I cannot generate the explanation yet."
    if intent == "debug":
        return f"I received {line_count} selected line(s). Ollama is unavailable, so I cannot analyze the failure yet."
    if intent == "review":
        return f"I received {line_count} selected line(s). Ollama is unavailable, so I cannot review the code yet."
    return f"I received {line_count} selected line(s). Ollama is unavailable, so I cannot answer yet."


def parse_orchestrator_response(response: str) -> dict[str, Any]:
    text = strip_json_markdown(response.strip())
    candidates = list(orchestrator_json_candidates(text))
    errors: list[str] = []

    for candidate in candidates:
        for repaired in repair_json_candidates(candidate):
            try:
                parsed = json.loads(repaired)
            except json.JSONDecodeError as error:
                errors.append(str(error))
                continue
            return validate_orchestrator_payload(parsed)

        try:
            parsed = ast.literal_eval(candidate)
        except (SyntaxError, ValueError) as error:
            errors.append(str(error))
            continue
        return validate_orchestrator_payload(parsed)

    detail = "; ".join(errors[-2:]) if errors else "No JSON object found."
    raise ValueError(f"Could not parse orchestrator JSON. {detail}")


def strip_json_markdown(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    return fenced.group(1).strip() if fenced else text


def orchestrator_json_candidates(text: str) -> list[str]:
    candidates = [text]
    decoder = json.JSONDecoder()
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            _, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        candidates.append(text[start:start + end])

    greedy = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if greedy:
        candidates.append(greedy.group(0))

    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip()
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def repair_json_candidates(text: str) -> list[str]:
    normalized = text.strip()
    missing_comma_repaired = re.sub(
        r'("[^"\\]*(?:\\.[^"\\]*)*")\s+("[A-Za-z_][A-Za-z0-9_]*"\s*:)',
        r"\1, \2",
        normalized,
    )
    trailing_comma_repaired = re.sub(r",\s*([}\]])", r"\1", missing_comma_repaired)
    quote_repaired = trailing_comma_repaired.replace("“", '"').replace("”", '"').replace("’", "'")
    candidates = [
        normalized,
        missing_comma_repaired,
        trailing_comma_repaired,
        quote_repaired,
    ]
    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def validate_orchestrator_payload(parsed: Any) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        raise ValueError("Orchestrator response was not a JSON object.")

    intent = normalize_intent(parsed.get("intent"))
    route = normalize_route(parsed.get("route")) or route_for_intent(intent)
    confidence = clamp_float(parsed.get("confidence"), default=0.5)
    needs_clarification = bool(parsed.get("needsClarification", route == "clarify"))
    clarifying_question = _clean(parsed.get("clarifyingQuestion"))

    return {
        "intent": intent,
        "route": route,
        "confidence": confidence,
        "needsClarification": needs_clarification,
        "clarifyingQuestion": clarifying_question,
    }


def _safe_log_snippet(value: Any, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "..."


def normalize_intent(value: Any) -> Intent:
    intent = _clean(value)
    allowed = {
        "chat",
        "explain",
        "debug",
        "review",
        "fix",
        "refactor",
        "replace",
        "write_test",
        "clarify",
        "unknown",
    }
    if intent in allowed:
        return intent  # type: ignore[return-value]
    return "unknown"


def normalize_route(value: Any) -> Route | None:
    route = _clean(value)
    if route in {"answer", "patch", "clarify"}:
        return route  # type: ignore[return-value]
    return None


def clamp_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def default_clarifying_question(intent: str) -> str:
    if intent == "clarify":
        return "What would you like to do next?"
    return "Do you want to talk generally, or do you want help with selected code?"


def validate_project_root(project_root: str) -> str:
    try:
        path = Path(project_root).expanduser().resolve()
    except OSError as error:
        return f"Project folder path is invalid: {error}"

    if not path.exists():
        return "Project folder does not exist. Choose a valid project folder."
    if not path.is_dir():
        return "Project root must be a folder."

    home = Path.home().resolve()
    if path == Path(path.anchor).resolve():
        return "Project root is too broad. Choose the specific project folder."
    if path == home:
        return "Project root is your home folder, which is too broad. Choose the specific project folder."

    return ""


def validate_file_path_inside_project(file_path: str, project_root: str) -> str:
    if not file_path:
        return ""
    try:
        root = Path(project_root).expanduser().resolve()
        file = Path(file_path).expanduser().resolve()
    except OSError as error:
        return f"File path could not be validated: {error}"
    if root not in file.parents and file != root:
        return "File path is outside the approved project root; ignoring filePath for context."
    return ""


def is_allowed_test_command(command: list[str]) -> bool:
    if not command:
        return False
    normalized = [part.strip() for part in command if part.strip()]
    allowed = {
        ("npm", "test"),
        ("npm", "run", "test"),
        ("pnpm", "test"),
        ("pnpm", "run", "test"),
        ("yarn", "test"),
        ("pytest",),
        ("python", "-m", "pytest"),
        ("python3", "-m", "pytest"),
        ("uv", "run", "pytest"),
    }
    return tuple(normalized) in allowed
