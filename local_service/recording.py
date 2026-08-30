import tempfile
from pathlib import Path


def record_microphone(duration_seconds: float) -> Path:
    try:
        import sounddevice as sd
        import soundfile as sf
    except ImportError as error:
        raise RuntimeError("Install sounddevice and soundfile to enable local microphone recording.") from error

    duration = min(max(float(duration_seconds or 8.0), 2.0), 20.0)
    sample_rate = 16000

    audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype="float32")
    sd.wait()

    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    temp_path = Path(temp_file.name)
    temp_file.close()
    sf.write(temp_path, audio, sample_rate, format="WAV")
    return temp_path
