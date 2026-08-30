import os
from pathlib import Path

_model = None
_model_key = None


def transcribe_audio(audio_path: Path, model_name: str | None = None) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise RuntimeError("Install faster-whisper to enable speech-to-text.") from error

    model_name = model_name or os.getenv("WHISPER_MODEL", "small.en")
    device = os.getenv("WHISPER_DEVICE", "cpu")
    compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
    model = get_model(WhisperModel, model_name, device, compute_type)

    segments, _info = model.transcribe(str(audio_path), beam_size=5)
    return " ".join(segment.text.strip() for segment in segments).strip()


def get_model(whisper_model_class, model_name: str, device: str, compute_type: str):
    global _model, _model_key
    key = (model_name, device, compute_type)
    if _model is None or _model_key != key:
        _model = whisper_model_class(model_name, device=device, compute_type=compute_type)
        _model_key = key
    return _model
