import time
from collections import deque
from typing import Dict, Optional
from uuid import uuid4

from pydantic import BaseModel

from app.services.transcript import TranscriptAccumulator
from app.ai_router import is_model_available
from app.services.complete_settings import get_complete_settings


# =========================================================
# GLOBAL SESSION CACHE (IN-MEMORY)
# =========================================================
SESSION_CACHE: Dict[str, Dict] = {}


# =========================================================
# LOG HELPER
# =========================================================
def log(message: str, level: str = "INFO"):
    timestamp = time.strftime("%H:%M:%S")
    prefix = {
        "INFO": "ℹ️",
        "SUCCESS": "✅",
        "ERROR": "❌",
        "WARNING": "⚠️",
        "DEBUG": "🔍",
    }.get(level, "")
    print(f"[{timestamp}] {prefix} {message}", flush=True)


# =========================================================
# CANDIDATE CONTEXT CACHE
# =========================================================
class CandidateSessionCache:
    def __init__(self, max_chars: int = 6000):
        self.full_transcript = []
        self.max_chars = max_chars

    def add(self, text: str):
        if text and text.strip():
            self.full_transcript.append(text.strip())

    def get_context(self) -> str:
        merged = " ".join(self.full_transcript)
        return merged[-self.max_chars:]


# =========================================================
# SESSION INIT REQUEST SCHEMA
# =========================================================
class SessionInitRequest(BaseModel):
    user_id: str
    persona_id: Optional[str] = None
    resume_path: Optional[str] = None
    custom_style_prompt: Optional[str] = None


# =========================================================
# SESSION CREATION (Prompt-1 owner)
# =========================================================
async def create_session(request: SessionInitRequest) -> Dict:
    session_id = str(uuid4())
    log(f"🚀 Initializing session: {session_id}")

    merged = await get_complete_settings(
        user_id=request.user_id,
        persona_id=request.persona_id,
        resume_path=request.resume_path,
    )

    settings = merged.get("settings", {})
    settings["responseStyleRow"] = merged.get("response_style") or {}

    persona_data = merged.get("persona") or {}
    cached_system_prompt = merged.get("system_prompt")

    model = settings.get("default_model")
    if model and not is_model_available(model):
        log(f"Model not available: {model}", "WARNING")

    SESSION_CACHE[session_id] = {
        "settings": settings,
        "persona_data": persona_data,
        "cached_system_prompt": cached_system_prompt,
        "custom_style_prompt": request.custom_style_prompt,
        "transcript_accumulator": TranscriptAccumulator(
            pause_threshold=float(settings.get("pause_interval", 2))
        ),
        "prev_questions": deque(maxlen=10),
        "candidate_cache": CandidateSessionCache(),
        "created_at": time.time(),
    }

    log(f"✅ Session cached: {session_id}", "SUCCESS")

    return {
        "session_id": session_id,
        "settings": settings,
        "persona_data": persona_data,
        "cached_system_prompt": cached_system_prompt,
    }


# =========================================================
# SESSION HELPERS
# =========================================================
def get_session(session_id: str) -> Optional[Dict]:
    return SESSION_CACHE.get(session_id)


def session_exists(session_id: str) -> bool:
    return session_id in SESSION_CACHE


def delete_session(session_id: str):
    if session_id in SESSION_CACHE:
        del SESSION_CACHE[session_id]
        log(f"🗑️ Session removed {session_id}", "SUCCESS")
