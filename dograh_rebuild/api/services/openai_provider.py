import base64
import os

import httpx


class ProviderConfigError(RuntimeError):
    pass


class ProviderRequestError(RuntimeError):
    pass


def _api_key():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ProviderConfigError("OPENAI_API_KEY is not configured")
    return api_key


def _base_url():
    return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")


def _headers():
    return {"Authorization": f"Bearer {_api_key()}"}


def _raise_provider_error(error: Exception):
    raise ProviderRequestError(str(error)) from error


def _extract_response_text(payload: dict):
    if payload.get("output_text"):
        return payload["output_text"]

    chunks = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                chunks.append(text)
    return "".join(chunks)


def generate_llm_response(system_prompt: str, graph_summary: str, user_text: str):
    input_text = "\n".join(
        [
            "You are running this voice workflow graph:",
            graph_summary,
            "",
            "Reply to the caller's latest message.",
            f"Caller: {user_text}",
        ]
    )
    payload = {
        "model": os.getenv("OPENAI_LLM_MODEL", "gpt-5"),
        "instructions": system_prompt,
        "input": input_text,
    }
    try:
        response = httpx.post(
            f"{_base_url()}/responses",
            headers={**_headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        return _extract_response_text(response.json())
    except Exception as error:  # noqa: BLE001
        _raise_provider_error(error)


def transcribe_audio(audio_bytes: bytes, filename: str, content_type: str):
    try:
        response = httpx.post(
            f"{_base_url()}/audio/transcriptions",
            headers=_headers(),
            data={"model": os.getenv("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe")},
            files={"file": (filename, audio_bytes, content_type)},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["text"]
    except Exception as error:  # noqa: BLE001
        _raise_provider_error(error)


def synthesize_speech(text: str, voice: str):
    try:
        response = httpx.post(
            f"{_base_url()}/audio/speech",
            headers={**_headers(), "Content-Type": "application/json"},
            json={
                "model": os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
                "voice": voice,
                "input": text,
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.content
    except Exception as error:  # noqa: BLE001
        _raise_provider_error(error)


def encode_audio(audio_bytes: bytes):
    return base64.b64encode(audio_bytes).decode("ascii")


def decode_audio(audio_base64: str):
    return base64.b64decode(audio_base64.encode("ascii"), validate=True)
