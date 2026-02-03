# app/complete_settings.py
"""
Central loader that merges copilot settings, response style, and persona.
Builds a one-time compact system prompt (Prompt-1) that can be cached
per session to avoid repeated token usage during WebSocket flow.
"""

import asyncio
from typing import Optional, Dict, Any

from app.supabase_client import (
    fetch_user_settings,
    fetch_response_style,
    fetch_system_default_style,
    fetch_persona,
    fetch_user_resume_url,
    get_default_settings,
)

# =========================================================
# RESPONSE STYLE → COMPACT & ENFORCED PROMPT
# =========================================================
def _minimal_response_style_prompt(style_row: Dict[str, Any]) -> str:
    """
    Converts a response_style DB row into a strong, enforceable prompt block.
    Response length is treated as a REQUIREMENT, not a hint.
    """
    if not style_row:
        return ""

    parts = []

    if style_row.get("style_name"):
        parts.append(f"Style Name: {style_row.get('style_name')}")

    if style_row.get("tone"):
        parts.append(f"Tone: {style_row.get('tone')}")

    # 🔥 Enforced length
    length = style_row.get("approximate_length")
    if length:
        parts.append(
            f"LENGTH REQUIREMENT: Approximately {length}.\n"
            f"CRITICAL: Keep answers concise if the limit is low. "
            f"Do NOT give a long answer if {length} is requested."
        )

    if style_row.get("description"):
        parts.append(f"Description: {style_row.get('description')}")

    # Example (trimmed)
    if style_row.get("example_response"):
        example = style_row.get("example_response")[:500]
        parts.append(
            "Follow the structure, tone, and length shown below:"
        )
        parts.append(f"Example:\n{example}")

    return "\n".join(parts)


# =========================================================
# SYSTEM PROMPT BUILDER (PROMPT-1)
# =========================================================
def build_system_prompt_from_merged(
    settings: Dict[str, Any],
    response_style_row: Optional[Dict[str, Any]],
    persona: Optional[Dict[str, Any]],
) -> str:
    """
    Builds a compact but complete candidate-mode system prompt.
    Designed to be cached once per session.
    """

    style_block = (
        _minimal_response_style_prompt(response_style_row)
        if response_style_row
        else settings.get("response_style", "")
    )

    prompt = []

    # --- ROLE ---
    prompt.append(
        "You ARE the candidate in an interview. "
        "Answer as the candidate using 'I' and 'my experience'. "
        "Never say you are an AI or assistant."
    )

    # --- RESPONSE STYLE ---
    prompt.append("\n--- RESPONSE STYLE ---")
    prompt.append(style_block)

    # --- COPILOT SETTINGS ---
    prompt.append("\n--- COPILOT SETTINGS ---")
    prompt.append(
        f"Preferred language: {settings.get('audio_language', 'English')}"
    )
    prompt.append(
        f"Programming language preference: "
        f"{settings.get('programming_language', 'Python')}"
    )

    if settings.get("interview_instructions"):
        prompt.append(
            f"Extra interview instructions: "
            f"{settings.get('interview_instructions')}"
        )

    if settings.get("coding_instructions"):
        prompt.append(
            f"Extra coding instructions: "
            f"{settings.get('coding_instructions')}"
        )

    # --- PERSONA / RESUME ---
    if persona:
        prompt.append("\n--- CANDIDATE PROFILE ---")
        prompt.append(f"Position: {persona.get('position', '')}")
        prompt.append(f"Company: {persona.get('company_name', '')}")

        if persona.get("company_description"):
            prompt.append(
                f"Company description: {persona.get('company_description')}"
            )

        if persona.get("job_description"):
            prompt.append(
                f"Job description: {persona.get('job_description')}"
            )

        if persona.get("resume_text"):
            resume_snippet = persona.get("resume_text")[:5000]
            prompt.append("\nRESUME (context):")
            prompt.append(resume_snippet)
        elif persona.get("resume_url"):
            prompt.append(f"Resume URL: {persona.get('resume_url')}")

    # --- GLOBAL RULES ---
    prompt.append(
        "\n--- ANSWERING RULES ---\n"
        "- Always answer as the candidate.\n"
        "- Be professional, clear, and aligned with the selected style.\n"
        "- Default to the specified programming language for code.\n"
    )

    return "\n".join([p for p in prompt if p])


# =========================================================
# COMPLETE SETTINGS LOADER
# =========================================================
async def get_complete_settings(
    user_id: Optional[str],
    persona_id: Optional[str] = None,
    resume_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Returns a merged object:
    {
      'settings': {...},
      'response_style': {...} or None,
      'persona': {...} or None,
      'system_prompt': str or None
    }
    """

    # -----------------------------
    # 1. USER SETTINGS
    # -----------------------------
    if not user_id:
        settings = get_default_settings()
    else:
        settings = await asyncio.to_thread(
            fetch_user_settings, user_id
        )

    # -----------------------------
    # 2. RESPONSE STYLE
    # -----------------------------
    response_style_row = None
    selected_style_id = settings.get("selected_response_style_id")

    if selected_style_id:
        try:
            response_style_row = await asyncio.to_thread(
                fetch_response_style, selected_style_id
            )
        except Exception:
            response_style_row = None

    if not response_style_row:
        try:
            response_style_row = await asyncio.to_thread(
                fetch_system_default_style
            )
        except Exception:
            response_style_row = None

    # -----------------------------
    # 3. PERSONA
    # -----------------------------
    persona = None
    if persona_id:
        try:
            persona = await asyncio.to_thread(
                fetch_persona, persona_id
            )
        except Exception:
            persona = None

    if not persona and resume_path:
        persona = {
            "resume_url": await asyncio.to_thread(
                fetch_user_resume_url, resume_path
            )
        }

    # -----------------------------
    # 4. SYSTEM PROMPT (PROMPT-1)
    # -----------------------------
    system_prompt = None
    if response_style_row or (persona and persona.get("resume_text")):
        system_prompt = build_system_prompt_from_merged(
            settings, response_style_row, persona
        )

    return {
        "settings": settings,
        "response_style": response_style_row,
        "persona": persona,
        "system_prompt": system_prompt,
    }
