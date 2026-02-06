# app/session_manager.py

"""
Central session memory manager.

Responsibilities:
- Create session containers
- Read / restore session state
- Update cached fields safely
- Destroy sessions on end
- Optional TTL-based cleanup (future ready)

Used by:
- /session/init (HTTP)
- ws_live_interview (WebSocket)
"""

import time
from collections import deque
from typing import Dict, Optional
from uuid import uuid4

from app.services.transcript import TranscriptAccumulator


# =========================================================
# GLOBAL SESSION STORE
# =========================================================
SESSION_CACHE: Dict[str, Dict] = {}


# =========================================================
# SESSION CREATION
# =========================================================
def create_session(
    *,
    settings: dict,
    persona_data: dict,
    cached_system_prompt: Optional[str],
    custom_style_prompt: Optional[str],
) -> str:
    """
    Create a new session and store it in memory.
    Returns session_id.
    """
    session_id = str(uuid4())

    SESSION_CACHE[session_id] = {
        # immutable-ish
        "created_at": time.time(),

        # config
        "settings": settings,
        "persona_data": persona_data,
        "cached_system_prompt": cached_system_prompt,
        "custom_style_prompt": custom_style_prompt,

        # runtime state
        "transcript_accumulator": TranscriptAccumulator(
            pause_threshold=float(settings.get("pause_interval", 2))
        ),
        "prev_questions": deque(maxlen=10),
        "candidate_cache": _CandidateSessionCache(),
    }

    print(f"✅ [SessionManager] Created session {session_id}")
    return session_id


# =========================================================
# SESSION ACCESS
# =========================================================
def get_session(session_id: str) -> Optional[Dict]:
    """
    Fetch session from memory.
    """
    return SESSION_CACHE.get(session_id)


def session_exists(session_id: str) -> bool:
    return session_id in SESSION_CACHE


# =========================================================
# SESSION UPDATE HELPERS
# =========================================================
def update_cached_prompt(session_id: str, prompt: str):
    session = SESSION_CACHE.get(session_id)
    if session and prompt:
        session["cached_system_prompt"] = prompt
        print(f"🧠 [SessionManager] Cached system prompt updated ({session_id})")


def add_prev_question(session_id: str, question: str):
    session = SESSION_CACHE.get(session_id)
    if session and question:
        session["prev_questions"].append(question)


def add_candidate_context(session_id: str, text: str):
    session = SESSION_CACHE.get(session_id)
    if session and text:
        session["candidate_cache"].add(text)


# =========================================================
# SESSION RESET (PER QUESTION CYCLE)
# =========================================================
def reset_transcript_state(session_id: str):
    """
    Reset partial transcript state between interviewer questions.
    """
    session = SESSION_CACHE.get(session_id)
    if not session:
        return

    acc = session.get("transcript_accumulator")
    if acc:
        acc.reset()

    print(f"🔄 [SessionManager] Transcript state reset ({session_id})")


# =========================================================
# SESSION DESTRUCTION
# =========================================================
def delete_session(session_id: str):
    if session_id in SESSION_CACHE:
        del SESSION_CACHE[session_id]
        print(f"🗑️ [SessionManager] Session removed {session_id}")


# =========================================================
# OPTIONAL: TTL CLEANUP (NOT AUTO-RUN)
# =========================================================
def cleanup_expired_sessions(ttl_seconds: int = 3600):
    """
    Removes sessions older than ttl_seconds.
    Safe to run from a background task / cron.
    """
    now = time.time()
    expired = [
        sid
        for sid, sess in SESSION_CACHE.items()
        if now - sess.get("created_at", now) > ttl_seconds
    ]

    for sid in expired:
        delete_session(sid)

    if expired:
        print(f"🧹 [SessionManager] Cleaned {len(expired)} expired sessions")


# =========================================================
# INTERNAL: CANDIDATE CONTEXT CACHE
# =========================================================
class _CandidateSessionCache:
    """
    Rolling buffer of candidate responses for live context.
    """

    def __init__(self, max_chars: int = 6000):
        self.full_transcript = []
        self.max_chars = max_chars

    def add(self, text: str):
        if text and text.strip():
            self.full_transcript.append(text.strip())

    def get_context(self) -> str:
        merged = " ".join(self.full_transcript)
        return merged[-self.max_chars:]
