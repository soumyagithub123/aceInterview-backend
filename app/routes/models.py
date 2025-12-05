from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.supabase_client import supabase

router = APIRouter(prefix="/api/models")

# List of all models supported by your system
ALL_MODELS = [
    "gpt-3.0-mini",
    "gpt-3.0",
    "gpt-3.1-mini",
    "gpt-3.1",
    "gpt-4.1-mini",
    "gpt-4.1",
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-o1-mini",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-pro",
    "ollama"
]


class SetModelRequest(BaseModel):
    provider: str
    user_id: str = None  # Optional for now


@router.get("/status")
def model_status():
    # Return available_providers as a dict with all models set to True
    available_providers = {model: True for model in ALL_MODELS}
    
    return {
        "status": "ok",
        "message": "Model API active",
        "all_models": ALL_MODELS,
        "available_providers": available_providers,
        "default_provider": "gpt-4o",
        "coding_provider": "gpt-4o"
    }


@router.post("/set-default")
def set_default_model(request: SetModelRequest):
    try:
        if request.provider not in ALL_MODELS:
            raise HTTPException(status_code=400, detail="Invalid model")

        # If user_id provided, update in Supabase
        if request.user_id:
            result = supabase.table("copilot_settings").update({
                "default_model": request.provider
            }).eq("user_id", request.user_id).execute()

            if len(result.data) == 0:
                raise HTTPException(status_code=404, detail="User settings not found")

        return {"success": True, "default_model": request.provider}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/set-coding")
def set_coding_model(request: SetModelRequest):
    try:
        if request.provider not in ALL_MODELS:
            raise HTTPException(status_code=400, detail="Invalid model")

        # If user_id provided, update in Supabase
        if request.user_id:
            result = supabase.table("copilot_settings").update({
                "coding_model": request.provider
            }).eq("user_id", request.user_id).execute()

            if len(result.data) == 0:
                raise HTTPException(status_code=404, detail="User settings not found")

        return {"success": True, "coding_model": request.provider}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))