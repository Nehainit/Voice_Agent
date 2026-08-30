import io
import os

_pipeline = None
_pipeline_lang_code = None


def synthesize_speech(text: str, voice: str | None = None) -> bytes:
    try:
        from kokoro import KPipeline
        import soundfile as sf
    except ImportError as error:
        raise RuntimeError("Install kokoro and soundfile to enable text-to-speech.") from error

    voice = voice or os.getenv("KOKORO_VOICE", "af_heart")
    lang_code = os.getenv("KOKORO_LANG_CODE", "a")
    pipeline = get_pipeline(KPipeline, lang_code)
    generator = pipeline(text[:1200], voice=voice)

    chunks = []
    sample_rate = 24000
    for _graphemes, _phonemes, audio in generator:
        chunks.append(audio)

    if not chunks:
        return b""

    try:
        import numpy as np
    except ImportError as error:
        raise RuntimeError("Install numpy to enable text-to-speech audio assembly.") from error

    buffer = io.BytesIO()
    sf.write(buffer, np.concatenate(chunks), sample_rate, format="WAV")
    return buffer.getvalue()


def get_pipeline(pipeline_class, lang_code: str):
    global _pipeline, _pipeline_lang_code
    if _pipeline is None or _pipeline_lang_code != lang_code:
        _pipeline = pipeline_class(lang_code=lang_code)
        _pipeline_lang_code = lang_code
    return _pipeline
