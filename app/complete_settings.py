# app/complete_settings.py
"""
Central loader that merges copilot_settings, response_style, and persona.
It also builds a first-time system prompt (if persona.resume_text exists)
to allow ws_live_interview to cache and reuse it (saves tokens).
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


def _minimal_response_style_prompt(style_row: Dict[str, Any]) -> str:
    """
    Convert a response_style row into a compact prompt portion.
    Uses approximate_length, tone, description, and example_response.
    """
    if not style_row:
        return ""
    parts = []
    parts.append(f"Style Name: {style_row.get('style_name','')}")
    parts.append(f"Tone: {style_row.get('tone','')}")
    parts.append(f"Length hint: {style_row.get('approximate_length','')}")
    if style_row.get("description"):
        parts.append(f"Description: {style_row.get('description')}")
    if style_row.get("example_response"):
        parts.append(f"Example: {style_row.get('example_response')[:500]}")
    return "\n".join(parts)


def build_system_prompt_from_merged(settings: Dict[str, Any], response_style_row: Optional[Dict[str, Any]], persona: Optional[Dict[str, Any]]) -> str:
    """
    Builds a candidate-mode system prompt using settings, response_style_row, and persona (if present).
    This prompt is intentionally concise yet complete so it can be cached for the session.
    """
    # Always instruct the model to ACT AS THE CANDIDATE.
    style_block = _minimal_response_style_prompt(response_style_row) if response_style_row else settings.get("response_style", "")

    prompt = []
    prompt.append("You ARE the candidate in an interview. Answer as the candidate using 'I' and 'my experience'. Never say you are an AI.")
    prompt.append("\n--- RESPONSE STYLE ---")
    prompt.append(style_block)
    prompt.append("\n--- COPILOT SETTINGS ---")
    # Add only relevant fields to keep prompt small
    prompt.append(f"Preferred language: {settings.get('audio_language','English')}")
    prompt.append(f"Programming language preference: {settings.get('programming_language','Python')}")
    if settings.get("interview_instructions"):
        prompt.append(f"Extra interview instructions: {settings.get('interview_instructions')}")
    if settings.get("coding_instructions"):
        prompt.append(f"Extra coding instructions: {settings.get('coding_instructions')}")

    # Persona / Resume
    if persona:
        prompt.append("\n--- CANDIDATE PROFILE ---")
        prompt.append(f"Position: {persona.get('position','')}")
        prompt.append(f"Company: {persona.get('company_name','')}")
        if persona.get("company_description"):
            prompt.append(f"Company description: {persona.get('company_description')}")
        if persona.get("job_description"):
            prompt.append(f"Job description: {persona.get('job_description')}")
        # If resume_text available, include it (helps avoid extra fetches)
        if persona.get("resume_text"):
            # keep resume snippet length-limited to avoid huge prompt blowups
            resume = persona.get("resume_text")[:5000]
            prompt.append("\nRESUME (context):")
            prompt.append(resume)
        elif persona.get("resume_url"):
            # If resume_text not present include the URL so model can be allowed to extract if needed externally
            prompt.append(f"Resume URL: {persona.get('resume_url')}")

    # Global answering rules (candidate-focused)
    prompt.append(
        "\n--- ANSWERING RULES ---\n"
        "- Always answer as the candidate ('I', 'my experience').\n"
        "- Provide concise, professional, and accurate answers following the selected style.\n"
        "- When giving code, default to the programming language specified above.\n"
    )

    return "\n".join([p for p in prompt if p])


async def get_complete_settings(user_id: Optional[str], persona_id: Optional[str] = None, resume_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns:
    {
      'settings': {...},                # normalized copilot settings
      'response_style': {...} or None,  # chosen or system default response style row
      'persona': {...} or None,         # persona row with resume_text if available
      'system_prompt': str or None      # built system prompt (only when resume_text present or style present)
    }
    """
    # 1. Load settings (safe)
    if not user_id:
        settings = get_default_settings()
    else:
        settings = await asyncio.to_thread(fetch_user_settings, user_id)

    # 2. Resolve response style
    response_style_row = None
    sel_style_id = settings.get("selected_response_style_id")
    if sel_style_id:
        try:
            response_style_row = await asyncio.to_thread(fetch_response_style, sel_style_id)
        except Exception:
            response_style_row = None
    if not response_style_row:
        # fallback to system default
        try:
            response_style_row = await asyncio.to_thread(fetch_system_default_style)
        except Exception:
            response_style_row = None

    # 3. Load persona (if provided)
    persona = None
    if persona_id:
        try:
            persona = await asyncio.to_thread(fetch_persona, persona_id)
        except Exception:
            persona = None

    # If persona not found but resume_path provided, synthesize persona with resume_url
    if not persona and resume_path:
        persona = {"resume_url": await asyncio.to_thread(fetch_user_resume_url, resume_path)}

    # 4. Build a system prompt if persona.resume_text OR response_style_row exists
    system_prompt = None
    # Build prompt using persona.resume_text when available to save further calls
    if response_style_row or (persona and persona.get("resume_text")):
        system_prompt = build_system_prompt_from_merged(settings, response_style_row, persona)

    return {
        "settings": settings,
        "response_style": response_style_row,
        "persona": persona,
        "system_prompt": system_prompt,
    }