import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .agent_contract import AgentRespondRequest, AgentRespondResponse
from .agent_responder import respond_to_agent_request, stream_agent_response
from .app_config import get_platform_config, save_app_config
from .llm import ask_ollama
from .prompts import build_prompt
from .recording import record_microphone
from .settings import RuntimeSettings, get_settings, provider_warning, save_settings
from .stt import transcribe_audio
from .tts import synthesize_speech


app = FastAPI(title="CodeDuck Local Voice Service")


class EditorContext(BaseModel):
    kind: str = "none"
    languageId: str = ""
    fileName: str = ""
    selectedText: str = ""
    surroundingText: str = ""


class AskRequest(BaseModel):
    mode: str = "debug"
    question: str = ""
    context: EditorContext = EditorContext()
    audioBase64: str | None = None
    mimeType: str | None = None
    durationSeconds: float = 8.0
    settings: RuntimeSettings | None = None


class AskResponse(BaseModel):
    transcript: str = ""
    answer: str = ""
    audioBase64: str = ""
    audioMimeType: str = "audio/wav"
    warnings: list[str] = Field(default_factory=list)


class TTSRequest(BaseModel):
    text: str = ""
    settings: RuntimeSettings | None = None


class TTSResponse(BaseModel):
    audioBase64: str = ""
    audioMimeType: str = "audio/wav"
    warnings: list[str] = Field(default_factory=list)


@app.get("/health")
def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "ok": True,
        "ollama_model": settings.llmModel,
        "whisper_model": settings.sttModel,
        "tts_enabled": settings.ttsProvider != "off",
        "settings": settings.model_dump(),
    }


@app.get("/settings", response_model=RuntimeSettings)
def read_settings() -> RuntimeSettings:
    return get_settings()


@app.get("/platform/config")
def read_platform_config() -> dict[str, Any]:
    return get_platform_config()


@app.post("/platform/config/app")
def update_app_platform_config(update: dict[str, Any]) -> dict[str, Any]:
    return save_app_config(update)


@app.post("/settings", response_model=RuntimeSettings)
def update_settings(settings: RuntimeSettings) -> RuntimeSettings:
    return save_settings(settings.model_dump())


@app.post("/agent/respond", response_model=AgentRespondResponse)
async def agent_respond(request: AgentRespondRequest) -> AgentRespondResponse:
    return await respond_to_agent_request(request)


@app.post("/tts/synthesize", response_model=TTSResponse)
async def tts_synthesize(request: TTSRequest) -> TTSResponse:
    settings = request.settings or get_settings()
    text = request.text.strip()
    if not text:
        return TTSResponse(warnings=["No text was provided for TTS."])
    if settings.ttsProvider == "off":
        return TTSResponse(warnings=["TTS is disabled."])
    try:
        audio_bytes = synthesize_speech(text, voice=settings.ttsVoice)
    except Exception as error:
        return TTSResponse(warnings=[f"Text-to-speech failed: {error}"])
    return TTSResponse(audioBase64=base64.b64encode(audio_bytes).decode("utf-8"))


@app.post("/agent/respond/stream")
async def agent_respond_stream(request: AgentRespondRequest) -> StreamingResponse:
    async def event_stream():
        async for event in stream_agent_response(request):
            payload = json.dumps(event.model_dump(), ensure_ascii=False)
            yield f"data: {payload}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/ask-text", response_model=AskResponse)
async def ask_text(request: AskRequest) -> AskResponse:
    transcript = request.question.strip()
    return await answer_question(request, transcript)


@app.post("/ask-audio", response_model=AskResponse)
async def ask_audio(request: AskRequest) -> AskResponse:
    warnings: list[str] = []
    if not request.audioBase64:
        return AskResponse(warnings=["No audio payload was received."])

    suffix = suffix_for_mime_type(request.mimeType)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_audio:
        temp_audio.write(base64.b64decode(request.audioBase64))
        temp_path = Path(temp_audio.name)

    try:
        settings = request.settings or get_settings()
        transcript = transcribe_audio(temp_path, model_name=settings.sttModel)
    except Exception as error:
        transcript = ""
        warnings.append(f"Speech-to-text failed: {error}")
    finally:
        temp_path.unlink(missing_ok=True)

    if not transcript:
        return AskResponse(warnings=warnings or ["No speech was transcribed."])

    response = await answer_question(request, transcript)
    response.warnings = warnings + response.warnings
    return response


@app.post("/ask-recording", response_model=AskResponse)
async def ask_recording(request: AskRequest) -> AskResponse:
    warnings: list[str] = []

    try:
        temp_path = record_microphone(request.durationSeconds)
    except Exception as error:
        return AskResponse(warnings=[f"Local microphone recording failed: {error}"])

    try:
        settings = request.settings or get_settings()
        transcript = transcribe_audio(temp_path, model_name=settings.sttModel)
    except Exception as error:
        transcript = ""
        warnings.append(f"Speech-to-text failed: {error}")
    finally:
        temp_path.unlink(missing_ok=True)

    if not transcript:
        return AskResponse(warnings=warnings or ["No speech was transcribed."])

    response = await answer_question(request, transcript)
    response.warnings = warnings + response.warnings
    return response


async def answer_question(request: AskRequest, transcript: str) -> AskResponse:
    warnings: list[str] = []
    settings = request.settings or get_settings()
    prompt = build_prompt(mode=request.mode, question=transcript, context=request.context.model_dump())

    for warning in [
        provider_warning(settings.llmProvider, "ollama", "LLM"),
        provider_warning(settings.sttProvider, "faster-whisper", "STT"),
    ]:
        if warning:
            warnings.append(warning)

    try:
        answer = await ask_ollama(prompt, model=settings.llmModel, num_ctx=settings.numCtx)
    except Exception as error:
        return AskResponse(
            transcript=transcript,
            warnings=[f"Ollama request failed: {error}"],
        )

    audio_base64 = ""
    if settings.ttsProvider != "off":
        warning = provider_warning(settings.ttsProvider, "kokoro", "TTS")
        if warning:
            warnings.append(warning)
        try:
            audio_bytes = synthesize_speech(answer, voice=settings.ttsVoice)
            if audio_bytes:
                audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
        except Exception as error:
            warnings.append(f"Text-to-speech skipped: {error}")

    return AskResponse(
        transcript=transcript,
        answer=answer,
        audioBase64=audio_base64,
        warnings=warnings,
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
