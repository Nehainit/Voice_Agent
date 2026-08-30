from __future__ import annotations

import asyncio
import base64
import difflib
import tempfile
import time
from pathlib import Path
from typing import AsyncIterator
import re

from .agent_contract import (
    AgentAction,
    AgentError,
    AgentRespondRequest,
    AgentRespondResponse,
    AgentStreamEvent,
    PatchProposal,
    TaskSnapshot,
    TestResult,
)
from .agent_graph import answer_node, classify_intent_node, input_node, is_allowed_test_command, llm_orchestrator_node, patch_node, project_context_gate_node, route_after_intent, run_tests_node
from .agent_registry import resolve_agent, response_language
from .app_config import get_app_config
from .settings import RuntimeSettings, get_settings, provider_warning
from .stt import transcribe_audio
from .tts import synthesize_speech
from .session_state import get_session_context, update_session_context, update_task_memory


async def respond_to_agent_request(request: AgentRespondRequest) -> AgentRespondResponse:
    settings = request.settings or get_settings()
    transcript, transcript_warnings, transcript_error = await transcript_for_request(request, settings)
    agent = resolve_agent(transcript or request.commandText, request.activeAgentId, request.context.model_dump())
    language = response_language(request.preferredResponseLanguage, agent)
    keep_terms = bool(get_app_config().get("language", {}).get("keepTechnicalTermsEnglish", True))
    if transcript_error:
        response = AgentRespondResponse(
            ok=False,
            requestId=request.requestId,
            inputMode=request.inputMode,
            activeAgentId=agent.agent_id,
            uiState="error",
            intent="unknown",
            transcript=transcript,
            actions=["retry", "close"],
            warnings=transcript_warnings,
            error=transcript_error,
        )
        return await finalize_response(response, settings, request=request, agent_id=agent.agent_id)

    selected_text = request.context.selectedText.strip()
    session_context = get_session_context()

    control_response = control_response_for_transcript(request, transcript, transcript_warnings)
    if control_response:
        response = control_response
        return await finalize_response(response, settings, request=request, selected_text=selected_text, agent_id=agent.agent_id)

    if request.inputMode == "dictation":
        response = AgentRespondResponse(
            requestId=request.requestId,
            inputMode="dictation",
            activeAgentId=agent.agent_id,
            uiState="dictation_result",
            intent="chat",
            transcript=transcript,
            answer=transcript,
            spokenAnswer="",
            draftText=transcript,
            actions=["paste_to_focused_app", "copy"],
            actionPlans=[
                AgentAction(
                    type="paste_to_focused_app",
                    requiresApproval=False,
                    payload={"text": transcript},
                )
            ],
            warnings=transcript_warnings,
        )
        return await finalize_response(response, settings, request=request, selected_text=selected_text, agent_id=agent.agent_id, skip_tts=True)

    if request.execution.allowTestRun:
        state = await run_tests_node(
            input_node(
                {
                    "command_text": transcript,
                    "context": request.context.model_dump(),
                    "allow_test_run": request.execution.allowTestRun,
                    "test_command": request.execution.testCommand,
                    "test_iterations": request.execution.testIterations or settings.testIterations,
                    "working_directory": request.execution.workingDirectory,
                    "warnings": transcript_warnings,
                    "session_context": session_context,
                    "agent_id": agent.agent_id,
                    "agent_name": agent.name,
                    "response_language": language,
                    "keep_technical_terms_english": keep_terms,
                }
            )
        )
        status = state.get("test_status", "skipped")
        response = AgentRespondResponse(
            requestId=request.requestId,
            uiState="test_result",
            intent="unknown",
            transcript=transcript,
            answer=test_answer(status),
            testResult=TestResult(
                status=status,
                command=request.execution.testCommand,
                workingDirectory=request.execution.workingDirectory,
                iterations=state.get("test_iterations", request.execution.testIterations),
                exitCode=state.get("test_exit_code"),
                output=state.get("test_output", ""),
                durationSeconds=state.get("test_duration_seconds", 0.0),
            ),
            actions=["copy", "close"],
            warnings=state.get("warnings", []),
        )
        return await finalize_response(response, settings, request=request, selected_text=selected_text, agent_id=agent.agent_id)

    state = classify_intent_node(
        input_node(
            {
                "command_text": transcript,
                "context": request.context.model_dump(),
                "warnings": transcript_warnings,
                "session_context": session_context,
                "agent_id": agent.agent_id,
                "agent_name": agent.name,
                "response_language": language,
                "keep_technical_terms_english": keep_terms,
            }
        )
    )
    state = await llm_orchestrator_node(
        state,
        model=settings.llmModel,
        num_ctx=settings.numCtx,
    )
    intent = state.get("intent", "unknown")
    route = route_after_intent(state)

    if route == "clarify":
        response = AgentRespondResponse(
            requestId=request.requestId,
            uiState="needs_clarification",
            intent="clarify" if intent == "clarify" else "unknown",
            transcript=transcript,
            answer=clarification_message(state, selected_text),
            actions=["reply", "close"],
            warnings=state.get("warnings", []),
        )
        return await finalize_response(response, settings, request=request, selected_text=selected_text, agent_id=agent.agent_id)

    if route == "patch":
        if not selected_text:
            response = AgentRespondResponse(
                requestId=request.requestId,
                uiState="needs_clarification",
                intent="clarify",
                transcript=transcript,
                answer="Highlight the code you want me to change, or tell me the file and task more specifically.",
                actions=["reply", "close"],
                warnings=state.get("warnings", []),
            )
            return await finalize_response(response, settings, request=request, selected_text=selected_text, agent_id=agent.agent_id)

        state = project_context_gate_node(state)
        project_context_status = state.get("project_context_status")
        if project_context_status == "needs_project_root":
            response = AgentRespondResponse(
                requestId=request.requestId,
                uiState="needs_project_root",
                intent=intent,
                transcript=transcript,
                answer=state.get("project_context_message", "Choose the project folder so I can inspect related files before proposing a safer fix."),
                actions=["choose_project_root", "continue_selected_only", "cancel"],
                warnings=state.get("warnings", []),
            )
            return await finalize_response(response, settings, request=request, selected_text=selected_text, agent_id=agent.agent_id)
        if project_context_status == "invalid":
            response = AgentRespondResponse(
                ok=False,
                requestId=request.requestId,
                uiState="error",
                intent=intent,
                transcript=transcript,
                actions=["retry", "close"],
                warnings=state.get("warnings", []),
                error=AgentError(
                    code="invalid_project_root",
                    message=state.get("project_context_message", "Project root is invalid."),
                ),
            )
            return await finalize_response(response, settings, request=request, selected_text=selected_text, agent_id=agent.agent_id)

        state["patch_iterations"] = settings.patchIterations
        state = await patch_node(
            state,
            model=settings.llmModel,
            num_ctx=settings.numCtx,
        )
        proposed_code = state.get("proposed_code", "")
        diff = "\n".join(
            difflib.unified_diff(
                selected_text.splitlines(),
                proposed_code.splitlines(),
                fromfile="selected",
                tofile="proposed",
                lineterm="",
            )
        )
        if not proposed_code.strip() or not diff.strip():
            response = AgentRespondResponse(
                ok=False,
                requestId=request.requestId,
                uiState="error",
                intent=intent,
                transcript=transcript,
                actions=["retry", "close"],
                warnings=state.get("warnings", []),
                error=AgentError(
                    code="patch_generation_failed",
                    message="Could not generate a meaningful replacement for the selected code.",
                ),
            )
            return await finalize_response(response, settings, request=request, selected_text=selected_text, agent_id=agent.agent_id)
        response = AgentRespondResponse(
            requestId=request.requestId,
            uiState="patch_preview",
            intent=intent,
            transcript=transcript,
            answer=state.get("answer", "I prepared a replacement preview. Review the diff before applying it."),
            proposal=PatchProposal(
                proposalId=f"prop_{request.requestId}",
                title=state.get("patch_title", "Replacement preview"),
                originalCode=selected_text,
                proposedCode=proposed_code,
                diff=diff,
                languageId=request.context.languageId,
            ),
            actions=["apply", "modify", "copy", "cancel"],
            actionPlans=[AgentAction(type="show_patch_preview", requiresApproval=True, payload={"proposalId": f"prop_{request.requestId}"})],
            warnings=state.get("warnings", []),
        )
        return await finalize_response(response, settings, request=request, selected_text=selected_text, agent_id=agent.agent_id)

    state = await answer_node(
        state,
        model=settings.llmModel,
        num_ctx=settings.numCtx,
    )

    response = AgentRespondResponse(
        requestId=request.requestId,
        uiState="answer",
        intent=intent,
        transcript=transcript,
        answer=state.get("answer", ""),
        actions=["copy", "speak_again", "close"],
        warnings=state.get("warnings", []),
    )
    return await finalize_response(response, settings, request=request, selected_text=selected_text, agent_id=agent.agent_id)


async def finalize_response(
    response: AgentRespondResponse,
    settings: RuntimeSettings,
    *,
    request: AgentRespondRequest | None = None,
    selected_text: str = "",
    agent_id: str = "general_assistant",
    skip_tts: bool = False,
) -> AgentRespondResponse:
    task_snapshot = None
    if response.ok and response.transcript and response.answer:
        update_session_context(
            user_text=response.transcript,
            assistant_text=response.answer,
            intent=response.intent,
            ui_state=response.uiState,
            selected_text=selected_text,
        )
        task = update_task_memory(
            user_text=response.transcript,
            assistant_text=response.answer,
            intent=response.intent,
            ui_state=response.uiState,
            selected_text=selected_text,
            context=request.context.model_dump() if request else {},
            agent_id=agent_id,
        )
        if task:
            task_snapshot = TaskSnapshot(**task)

    response = response.model_copy(
        update={
            "inputMode": request.inputMode if request else response.inputMode,
            "activeAgentId": agent_id,
            "mindState": task_snapshot.status if task_snapshot else response.mindState,
            "task": task_snapshot,
            "spokenAnswer": response.spokenAnswer or response.answer,
            "shouldListenAgain": False,
        }
    )
    if skip_tts:
        return response
    return await attach_tts(response, settings)


def clarification_message(state: dict, selected_text: str) -> str:
    if not selected_text:
        return "I’m listening. You can talk normally, or highlight code if you want code help."
    clarifying_question = state.get("clarifying_question")
    if clarifying_question:
        return str(clarifying_question)
    intent = state.get("intent")
    if intent == "unknown":
        return "Do you want a quick explanation, or should I change the code?"
    return "Tell me what you want to do with this selected code."


def control_response_for_transcript(
    request: AgentRespondRequest,
    transcript: str,
    warnings: list[str],
) -> AgentRespondResponse | None:
    if is_stop_command(transcript):
        return AgentRespondResponse(
            requestId=request.requestId,
            uiState="answer",
            intent="unknown",
            transcript=transcript,
            answer="Okay, I am shutting myself down. Keep working, press the shortcut when you need me again, and I will be back.",
            actions=["quit_app"],
            warnings=warnings,
        )
    if is_dismissal_command(transcript):
        return AgentRespondResponse(
            requestId=request.requestId,
            uiState="answer",
            intent="unknown",
            transcript=transcript,
            answer="Okay, I’ll stay quiet. Call me if you need me.",
            actions=["close"],
            warnings=warnings,
        )
    pause_ms = parse_pause_duration_ms(transcript)
    if pause_ms is not None:
        return AgentRespondResponse(
            requestId=request.requestId,
            uiState="answer",
            intent="unknown",
            transcript=transcript,
            answer=f"Okay, I’ll pause for {format_duration(pause_ms)}.",
            sleepMs=pause_ms,
            actions=["sleep"],
            warnings=warnings,
        )
    return None


def parse_pause_duration_ms(transcript: str) -> int | None:
    command = transcript.strip().lower().replace("’", "'")
    if not command:
        return None

    if not any(word in command for word in ("pause", "sleep", "quiet", "wait", "hold on", "ruk")):
        return None

    number_words = {
        "one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15,
        "twenty": 20, "thirty": 30,
    }
    match = re.search(r"(\d+(?:\.\d+)?)\s*(second|seconds|sec|secs|minute|minutes|min|mins|hour|hours|hr|hrs)", command)
    value = None
    unit = "minutes"
    if match:
        value = float(match.group(1))
        unit = match.group(2)
    else:
        for word, number in number_words.items():
            word_match = re.search(rf"\b{word}\b\s*(second|seconds|sec|secs|minute|minutes|min|mins|hour|hours|hr|hrs)", command)
            if word_match:
                value = float(number)
                unit = word_match.group(1)
                break

    if value is None:
        value = 2.0
        unit = "minutes"

    if unit.startswith(("second", "sec")):
        ms = int(value * 1000)
    elif unit.startswith(("hour", "hr")):
        ms = int(value * 60 * 60 * 1000)
    else:
        ms = int(value * 60 * 1000)

    return max(5_000, min(ms, 2 * 60 * 60 * 1000))


def format_duration(ms: int) -> str:
    seconds = round(ms / 1000)
    if seconds < 60:
        return f"{seconds} seconds"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} minute" + ("" if minutes == 1 else "s")
    hours = round(minutes / 60, 1)
    return f"{hours:g} hour" + ("" if hours == 1 else "s")


def is_dismissal_command(transcript: str) -> bool:
    command = transcript.strip().lower().replace("’", "'")
    if not command:
        return False
    dismissal_phrases = (
        "we don't need your help",
        "we dont need your help",
        "i don't need your help",
        "i dont need your help",
        "don't need your help",
        "dont need your help",
        "no need",
        "not now",
        "leave it",
        "leave me",
        "go away",
        "go back",
        "that's all",
        "thats all",
        "nothing else",
        "no thanks",
        "not required",
    )
    return any(phrase in command for phrase in dismissal_phrases)


def is_pause_command(transcript: str) -> bool:
    command = transcript.strip().lower()
    if not command:
        return False
    pause_phrases = (
        "pause",
        "pause listening",
        "pause for two minutes",
        "pause for 2 minutes",
        "sleep",
        "sleep mode",
        "go to sleep",
        "wait",
        "wait for two minutes",
        "wait for 2 minutes",
        "hold on",
        "ruk ja",
        "ruk jao",
        "thoda ruk",
    )
    if command in pause_phrases:
        return True
    return any(
        phrase in command
        for phrase in (
            "pause for two minutes",
            "pause for 2 minutes",
            "sleep mode",
            "go to sleep",
            "wait for two minutes",
            "wait for 2 minutes",
        )
    )


def is_stop_command(transcript: str) -> bool:
    command = normalize_voice_command(transcript)
    if not command:
        return False
    stop_phrases = (
        "stop",
        "stop this",
        "stop listening",
        "stop now",
        "stop yourself",
        "stop you",
        "close",
        "close codeduck",
        "close neha",
        "quit",
        "quit app",
        "exit",
        "exit app",
        "cancel",
        "shut down",
        "shutdown",
        "shut up",
        "be quiet",
        "bas",
        "bus",
        "ruk ja",
        "ruk jao",
        "band karo",
        "chup",
    )
    if command in stop_phrases:
        return True
    if command.startswith(("stop ", "close neha ", "quit app ", "exit app ")):
        return True
    return any(phrase in command for phrase in ("stop listening", "stop neha", "stop you", "close codeduck", "close neha", "quit app", "exit app", "band karo", "ruk jao"))


def normalize_voice_command(transcript: str) -> str:
    command = transcript.strip().lower().replace("’", "'")
    command = re.sub(r"[^a-z0-9' ]+", " ", command)
    command = re.sub(r"\s+", " ", command).strip()
    return command


async def stream_agent_response(request: AgentRespondRequest) -> AsyncIterator[AgentStreamEvent]:
    yield AgentStreamEvent(requestId=request.requestId, event="status", message="Request received")
    settings = request.settings or get_settings()

    if request.inputType == "audio":
        yield AgentStreamEvent(requestId=request.requestId, event="status", message="Transcribing audio")
        transcript, transcript_warnings, transcript_error = await transcript_for_request(request, settings)
        if transcript_error:
            response = AgentRespondResponse(
                ok=False,
                requestId=request.requestId,
                uiState="error",
                intent="unknown",
                transcript=transcript,
                actions=["retry", "close"],
                warnings=transcript_warnings,
                error=transcript_error,
            )
            yield AgentStreamEvent(requestId=request.requestId, event="error", message=transcript_error.message, data={"response": response.model_dump()})
            yield AgentStreamEvent(requestId=request.requestId, event="final", message="Failed", data={"response": response.model_dump()})
            return
        yield AgentStreamEvent(requestId=request.requestId, event="transcript", message=transcript, data={"transcript": transcript})
        request = request.model_copy(update={"inputType": "text", "commandText": transcript, "audioBase64": ""})

    if request.execution.allowTestRun:
        async for event in stream_test_response(request):
            yield event
        return

    yield AgentStreamEvent(requestId=request.requestId, event="status", message="Generating response")
    response = await respond_to_agent_request(request)
    if response.audioBase64:
        yield AgentStreamEvent(requestId=request.requestId, event="status", message="Speech response ready")
    yield AgentStreamEvent(
        requestId=request.requestId,
        event="final",
        message="Done",
        data={"response": response.model_dump()},
    )


async def stream_test_response(request: AgentRespondRequest) -> AsyncIterator[AgentStreamEvent]:
    command = list(request.execution.testCommand or [])
    working_directory = request.execution.workingDirectory
    test_iterations = max(1, min(int(request.execution.testIterations or 1), 5))
    started_at = time.monotonic()

    yield AgentStreamEvent(
        requestId=request.requestId,
        event="status",
        message="Preparing approved test command",
        data={"command": command, "workingDirectory": working_directory, "iterations": test_iterations},
    )

    if not command:
        response = test_response(
            request,
            "skipped",
            None,
            "Test run skipped because no test command was provided.",
            0.0,
            iterations=test_iterations,
        )
        yield AgentStreamEvent(requestId=request.requestId, event="final", message="Tests skipped", data={"response": response.model_dump()})
        return

    if not is_allowed_test_command(command):
        response = test_response(
            request,
            "error",
            None,
            f"Rejected test command: {' '.join(command)}",
            0.0,
            ["Test command was rejected by the backend allowlist."],
            iterations=test_iterations,
        )
        yield AgentStreamEvent(requestId=request.requestId, event="error", message="Rejected test command", data={"response": response.model_dump()})
        yield AgentStreamEvent(requestId=request.requestId, event="final", message="Tests not run", data={"response": response.model_dump()})
        return

    cwd = Path(working_directory or ".").expanduser().resolve()
    if not cwd.exists() or not cwd.is_dir():
        response = test_response(
            request,
            "error",
            None,
            f"Invalid working directory: {cwd}",
            0.0,
            ["Test working directory does not exist."],
            iterations=test_iterations,
        )
        yield AgentStreamEvent(requestId=request.requestId, event="error", message="Invalid working directory", data={"response": response.model_dump()})
        yield AgentStreamEvent(requestId=request.requestId, event="final", message="Tests not run", data={"response": response.model_dump()})
        return

    output_parts: list[str] = []
    exit_code: int | None = None
    for iteration in range(1, test_iterations + 1):
        yield AgentStreamEvent(
            requestId=request.requestId,
            event="status",
            message=f"Running test iteration {iteration}/{test_iterations}",
            data={"iteration": iteration, "iterations": test_iterations},
        )
        output_parts.append(f"--- Test iteration {iteration}/{test_iterations} ---\n")
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except OSError as error:
            response = test_response(
                request,
                "error",
                None,
                str(error),
                round(time.monotonic() - started_at, 3),
                [f"Test command failed to start: {error}"],
                iterations=test_iterations,
            )
            yield AgentStreamEvent(requestId=request.requestId, event="error", message="Test command failed to start", data={"response": response.model_dump()})
            yield AgentStreamEvent(requestId=request.requestId, event="final", message="Tests not run", data={"response": response.model_dump()})
            return

        assert process.stdout is not None
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace")
            output_parts.append(text)
            yield AgentStreamEvent(
                requestId=request.requestId,
                event="test_log",
                message=text.rstrip(),
                data={"chunk": text, "iteration": iteration, "iterations": test_iterations},
            )

        exit_code = await process.wait()
        if exit_code != 0:
            break

    output = "".join(output_parts)[-12000:]
    status = "passed" if exit_code == 0 else "failed"
    response = test_response(
        request,
        status,
        exit_code,
        output,
        round(time.monotonic() - started_at, 3),
        iterations=test_iterations,
    )
    yield AgentStreamEvent(requestId=request.requestId, event="final", message="Tests finished", data={"response": response.model_dump()})


def test_response(
    request: AgentRespondRequest,
    status: str,
    exit_code: int | None,
    output: str,
    duration_seconds: float,
    warnings: list[str] | None = None,
    iterations: int | None = None,
) -> AgentRespondResponse:
    return AgentRespondResponse(
        requestId=request.requestId,
        uiState="test_result",
        intent="unknown",
        transcript=request.commandText.strip(),
        answer=test_answer(status),
        testResult=TestResult(
            status=status,
            command=request.execution.testCommand,
            workingDirectory=request.execution.workingDirectory,
            iterations=iterations or request.execution.testIterations,
            exitCode=exit_code,
            output=output,
            durationSeconds=duration_seconds,
        ),
        actions=["copy", "close"],
        warnings=warnings or [],
    )


def test_answer(status: str) -> str:
    if status == "passed":
        return "Tests passed."
    if status == "failed":
        return "Tests failed. Review the streamed log before continuing."
    if status == "skipped":
        return "Tests were skipped."
    return "Tests could not be run."


async def transcript_for_request(
    request: AgentRespondRequest,
    settings: RuntimeSettings,
) -> tuple[str, list[str], AgentError | None]:
    if request.inputType == "text":
        return request.commandText.strip(), [], None

    warnings: list[str] = []
    if not request.audioBase64:
        return "", warnings, AgentError(code="audio_missing", message="No audio payload was received.")

    warning = provider_warning(settings.sttProvider, "faster-whisper", "STT")
    if warning:
        warnings.append(warning)

    suffix = suffix_for_mime_type(request.mimeType)
    try:
        audio_bytes = base64.b64decode(request.audioBase64)
    except Exception as error:
        return "", warnings, AgentError(code="audio_decode_failed", message=f"Audio payload could not be decoded: {error}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_audio:
        temp_audio.write(audio_bytes)
        temp_path = Path(temp_audio.name)

    try:
        transcript = await asyncio.to_thread(transcribe_audio, temp_path, settings.sttModel)
    except Exception as error:
        return "", warnings, AgentError(code="stt_failed", message=f"Speech-to-text failed: {error}")
    finally:
        temp_path.unlink(missing_ok=True)

    if not transcript:
        return "", warnings, AgentError(code="empty_transcript", message="No speech was transcribed.")

    if is_likely_silence_hallucination(transcript):
        warnings.append(f"Ignored likely silence hallucination: {transcript!r}")
        return "", warnings, AgentError(code="empty_transcript", message="No speech was transcribed.")

    return transcript, warnings, None


def is_likely_silence_hallucination(transcript: str) -> bool:
    normalized = re.sub(r"[^a-z0-9' ]+", " ", transcript.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return True
    silence_phrases = {
        "thank you very much",
        "thanks for watching",
        "thanks for watching this video",
        "you",
        "uh",
        "um",
        "hmm",
        "hm",
    }
    return normalized in silence_phrases


async def attach_tts(response: AgentRespondResponse, settings: RuntimeSettings) -> AgentRespondResponse:
    if not response.ok or not response.answer.strip() or settings.ttsProvider == "off":
        return response

    warnings = list(response.warnings)
    warning = provider_warning(settings.ttsProvider, "kokoro", "TTS")
    if warning:
        warnings.append(warning)

    try:
        audio_bytes = await asyncio.to_thread(synthesize_speech, response.answer, settings.ttsVoice)
    except Exception as error:
        warnings.append(f"Text-to-speech skipped: {error}")
        return response.model_copy(update={"warnings": warnings})

    if not audio_bytes:
        return response.model_copy(update={"warnings": warnings})

    return response.model_copy(
        update={
            "audioBase64": base64.b64encode(audio_bytes).decode("utf-8"),
            "audioMimeType": "audio/wav",
            "warnings": warnings,
        }
    )


def suffix_for_mime_type(mime_type: str | None) -> str:
    if not mime_type:
        return ".webm"
    if "wav" in mime_type:
        return ".wav"
    if "mp4" in mime_type:
        return ".mp4"
    if "ogg" in mime_type:
        return ".ogg"
    return ".webm"
