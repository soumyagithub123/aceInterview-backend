# app/routes/persona.py

from fastapi import APIRouter, HTTPException
import asyncio

from app.supabase_client import fetch_persona

router = APIRouter()

@router.get("/persona/{persona_id}")
async def get_persona(persona_id: str):
    """
    Fetch a full persona including resume_text.
    - Uses async thread calls for Supabase
    - No trimming
    - Persona is selected from frontend, so no heavy processing needed
    """

    try:
        # Supabase call (run in thread)
        persona = await asyncio.to_thread(fetch_persona, persona_id)

        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")

        return {
            "id": persona.get("id"),
            "user_id": persona.get("user_id"),
            "company_name": persona.get("company_name"),
            "company_description": persona.get("company_description"),
            "position": persona.get("position"),
            "job_description": persona.get("job_description"),

            # Resume Details
            "resume_url": persona.get("resume_url"),
            "resume_text": persona.get("resume_text"),  # full text included
            "resume_filename": persona.get("resume_filename"),
            "resume_file_path": persona.get("resume_file_path"),

            "is_sample": persona.get("is_sample", False)
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
