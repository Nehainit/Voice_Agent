import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel


SETTINGS_PATH = Path(__file__).with_name("runtime_settings.json")


class RuntimeSettings(BaseModel):
    llmProvider: str = "ollama"
    llmModel: str = "qwen2.5-coder:7b-instruct"
    sttProvider: str = "faster-whisper"
    sttModel: str = "small.en"
    ttsProvider: str = "off"
    ttsModel: str = "kokoro"
    ttsVoice: str = "af_heart"
    recordingSeconds: float = 8.0
    numCtx: int = 4096
    patchIterations: int = 1
    testIterations: int = 1


def get_settings() -> RuntimeSettings:
    values = RuntimeSettings().model_dump()

    if SETTINGS_PATH.exists():
        try:
            values.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass

    values.update(
        {
            "llmModel": os.getenv("OLLAMA_MODEL", values["llmModel"]),
            "sttModel": os.getenv("WHISPER_MODEL", values["sttModel"]),
            "ttsVoice": os.getenv("KOKORO_VOICE", values["ttsVoice"]),
            "numCtx": int(os.getenv("OLLAMA_NUM_CTX", str(values["numCtx"]))),
            "patchIterations": int(os.getenv("CODEDUCK_PATCH_ITERATIONS", str(values["patchIterations"]))),
            "testIterations": int(os.getenv("CODEDUCK_TEST_ITERATIONS", str(values["testIterations"]))),
        }
    )
    if "CODEDUCK_TTS" in os.environ:
        values["ttsProvider"] = "kokoro" if os.getenv("CODEDUCK_TTS", "0") != "0" else "off"

    return RuntimeSettings(**values)


def save_settings(update: dict[str, Any]) -> RuntimeSettings:
    current = get_settings().model_dump()
    current.update({key: value for key, value in update.items() if value is not None})
    settings = RuntimeSettings(**current)
    SETTINGS_PATH.write_text(json.dumps(settings.model_dump(), indent=2), encoding="utf-8")
    return settings


def provider_warning(provider: str, supported: str, capability: str) -> str | None:
    if provider == supported:
        return None
    return f"{capability} provider '{provider}' is selectable in the UI but not implemented yet. Using '{supported}' locally for now."
