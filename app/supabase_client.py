# app/supabase_client.py
from supabase import create_client, Client
import os
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List

load_dotenv()

SUPABASE_URL: str = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise ValueError("Supabase credentials are missing. Check your .env file.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

RESUME_BUCKET = "resumes"


def get_default_settings() -> dict:
    return {
        "default_model": "gpt-4o",
        "coding_model": "gpt-4o",
        "available_providers": {"gpt-4o": True, "gemini-2.0-flash": True},
        "response_style": "concise",
        "selected_response_style_id": None,
        "audio_language": "English",
        "pause_interval": 2,
        "advanced_question_detection": False,
        "message_direction": "bottom",
        "auto_scroll": True,
        "enable_candidate_voice": False,
        "candidate_voice_settings": {
            "pitch": 1.0,
            "speed": 1.0,
            "voice": "alloy",
            "provider": "openai",
        },
        "programming_language": "Python",
        "interview_instructions": "",
        "coding_instructions": "",
    }


# --------------------------
# Copilot settings
# --------------------------
def fetch_user_settings(user_id: Optional[str]) -> Dict[str, Any]:
    if not user_id or user_id == "anonymous":
        return get_default_settings()
    try:
        resp = (
            supabase.table("copilot_settings")
            .select("*")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
    except Exception as e:
        print(f"❌ Error fetching copilot_settings for {user_id}: {e}")
        return get_default_settings()

    if not resp or not getattr(resp, "data", None):
        return get_default_settings()

    row = resp.data
    # Provide safe extraction
    return {
        "default_model": row.get("default_model") or "gpt-4o",
        "coding_model": row.get("coding_model") or "gpt-4o",
        "available_providers": row.get("available_providers")
        or {"gpt-4o": True, "gemini-2.0-flash": True},
        "response_style": row.get("response_style", "concise"),
        "selected_response_style_id": row.get("selected_response_style_id"),
        "audio_language": row.get("audio_language", "English"),
        "pause_interval": row.get("pause_interval", 2),
        "advanced_question_detection": row.get("advanced_question_detection", False),
        "message_direction": row.get("message_direction", "bottom"),
        "auto_scroll": row.get("auto_scroll", True),
        "enable_candidate_voice": row.get("enable_candidate_voice", False),
        "candidate_voice_settings": row.get("candidate_voice_settings")
        or {
            "pitch": 1.0,
            "speed": 1.0,
            "voice": "alloy",
            "provider": "openai",
        },
        "programming_language": row.get("programming_language", "Python"),
        "interview_instructions": row.get("interview_instructions") or "",
        "coding_instructions": row.get("coding_instructions") or "",
        "selected_response_style_id": row.get("selected_response_style_id"),
    }


# --------------------------
# Response styles
# --------------------------
def fetch_response_style(style_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not style_id:
        return None
    try:
        resp = (
            supabase.table("response_styles")
            .select("*")
            .eq("id", style_id)
            .single()
            .execute()
        )
        if resp and getattr(resp, "data", None):
            return resp.data
    except Exception as e:
        print(f"❌ Error fetching response_style {style_id}: {e}")
    return None


def fetch_system_default_style() -> Optional[Dict[str, Any]]:
    try:
        resp = (
            supabase.table("response_styles")
            .select("*")
            .eq("is_system_default", True)
            .limit(1)
            .execute()
        )
        if resp and getattr(resp, "data", None) and len(resp.data) > 0:
            return resp.data[0]
    except Exception as e:
        print(f"❌ Error fetching system default style: {e}")
    return None


# --------------------------
# Personas
# --------------------------
def fetch_persona(persona_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not persona_id:
        return None
    try:
        resp = (
            supabase.table("personas")
            .select("*")
            .eq("id", persona_id)
            .single()
            .execute()
        )
        if resp and getattr(resp, "data", None):
            return resp.data
    except Exception as e:
        print(f"❌ Error fetching persona {persona_id}: {e}")
    return None


def fetch_personas_for_user(user_id: str) -> List[Dict[str, Any]]:
    if not user_id:
        return []
    try:
        resp = (
            supabase.table("personas")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        if resp and getattr(resp, "data", None):
            return resp.data
    except Exception as e:
        print(f"❌ Error fetching personas for user {user_id}: {e}")
    return []


# --------------------------
# Resume URL builder
# --------------------------
def fetch_user_resume_url(file_path: str) -> str:
    if not file_path or not isinstance(file_path, str):
        return ""
    return f"{SUPABASE_URL}/storage/v1/object/public/{RESUME_BUCKET}/{file_path}"


def fetch_user_models(user_id: str) -> Dict[str, str]:
    settings = fetch_user_settings(user_id)
    return {"default_model": settings.get("default_model", "gpt-4o"), "coding_model": settings.get("coding_model", "gpt-4o")}


def get_supabase_client() -> Client:
    return supabase