from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.openai_tts import text_to_speech_base64

router = APIRouter(prefix="/api/voice", tags=["voice"])


# ---------------------------------------------------------
# Request schema
# ---------------------------------------------------------
class VoiceRequest(BaseModel):
    text: str
    voice: str | None = None
    model: str | None = None


# ---------------------------------------------------------
# Text → Voice endpoint
# ---------------------------------------------------------
@router.post("")
async def generate_voice(payload: VoiceRequest):
    """
    Converts given text into AI voice (base64 audio).
    Used in mock-interview mode for AI interviewer voice.
    """

    if not payload.text or not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text is required for voice generation")

    try:
        audio_base64 = text_to_speech_base64(
            text=payload.text,
            voice=payload.voice or "alloy",
            model=payload.model or "gpt-4o-mini-tts",
        )

        if not audio_base64:
            raise RuntimeError("Empty audio response from TTS")

        return {
            "audio": audio_base64,
            "voice": payload.voice or "alloy",
            "model": payload.model or "gpt-4o-mini-tts",
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Voice generation failed: {str(e)}"
        )
