from fastapi import APIRouter

from api.schemas.voice import VoiceTurnRequest
from api.services.voice_pipeline import run_voice_turn

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/test-turn")
def test_voice_turn(request: VoiceTurnRequest):
    return run_voice_turn(request.audio_text)
