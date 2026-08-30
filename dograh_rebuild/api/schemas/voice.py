from pydantic import BaseModel


class VoiceTurnRequest(BaseModel):
    audio_text: str
