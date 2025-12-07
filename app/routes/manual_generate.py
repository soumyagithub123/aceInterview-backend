# app/routes/manual_generate.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.ai_router import ask_ai

router = APIRouter(prefix="/api")


# ---------------------------------------------------------
# Request Schema
# ---------------------------------------------------------
class ManualGenerateRequest(BaseModel):
    user_id: str
    message: str
    model: str


# ---------------------------------------------------------
# Manual Chat Generation Endpoint
# ---------------------------------------------------------
@router.post("/manual-generate")
async def manual_generate(data: ManualGenerateRequest):
    """
    Allows frontend to manually generate an AI answer
    outside the live-transcription WebSocket pipeline.

    Uses the unified AI router (GPT / Gemini) for consistency.
    """
    try:
        if not data.message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty.")

        # Build OpenAI-style messages array
        system_prompt = (
            "You are an AI interview assistant.\n"
            "Provide clear, structured, helpful, and professional responses.\n"
            "Always answer as if guiding a candidate.\n"
            "Do NOT reply as an AI — reply as a human expert mentor."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": data.message.strip()}
        ]

        # Route to correct provider (OpenAI / Gemini)
        answer = await ask_ai(data.model, messages)

        if not answer or str(answer).strip() == "":
            return {
                "answer": None,
                "error": "AI returned an empty response."
            }

        return {
            "answer": answer,
            "model_used": data.model
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Manual generation failed: {str(e)}"
        )