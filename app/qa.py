# app/qa.py
import asyncio
from typing import Optional, Dict, Any

from app.ai_router import ask_ai

# Local fallback response styles (used only when DB style missing)
RESPONSE_STYLES = {
    "concise": {
        "name": "Concise Professional",
        "prompt": "Short, sharp, confident answers (6–10 sentences)."
    },
    "detailed": {
        "name": "Detailed Professional",
        "prompt": "Long, structured answers with examples and metrics (~200-350 words)."
    },
    "storytelling": {
        "name": "Storytelling (STAR)",
        "prompt": "Answer using STAR (Situation, Task, Action, Result) when relevant."
    },
    "technical": {
        "name": "Technical Expert",
        "prompt": "Deep technical answers; include code examples and rationale where helpful."
    }
}

# Detection prompt instructs the model to return QUESTION / ANSWER or SKIP
QUESTION_DETECTION_PROMPT = """
You are the CANDIDATE in an interview. Always answer as the candidate in first person ("I", "my").
Detect whether the incoming user speech is:
1) A direct question asked to the candidate.
2) A request for the assistant to ask the candidate a question.
3) A request for a specific interviewer prompt.
4) A request to repeat a question.

If one of the above is detected:
- Convert it into a clear interviewer-style QUESTION.
- Then answer it as the candidate.

Output must be strictly formatted as:
QUESTION: <clean interviewer-style question>
ANSWER: <candidate-style answer>

If none of the intents above are present, return EXACTLY:
SKIP
"""


async def process_transcript_with_ai(
    transcript: str,
    settings: Dict[str, Any],
    persona_data: Optional[Dict[str, Any]] = None,
    custom_style_prompt: Optional[str] = None,
    cached_system_prompt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Returns:
    {
      has_question: bool,
      question: str | None,
      answer: str | None,
      cached_system_prompt: str | None  # returned only when we built it here (so caller can cache)
    }
    """

    print(f"--- QA INPUT: {transcript[:160]} ---")

    if not transcript or not transcript.strip():
        return {"has_question": False, "question": None, "answer": None}

    if not settings:
        return {"has_question": False, "question": None, "answer": None}

    # --------------------------------------------------
    # Load response style
    # --------------------------------------------------
    db_style = settings.get("responseStyleRow") or {}
    fallback_style_id = settings.get("response_style") or settings.get("responseStyle") or "concise"

    if db_style and not custom_style_prompt:
        style_prompt = (
            f"Response style: {db_style.get('style_name','')}\n"
            f"Tone: {db_style.get('tone','')}\n"
            f"Length hint: {db_style.get('approximate_length','')}\n"
            f"Example: {db_style.get('example_response','')[:800]}"
        )
    elif custom_style_prompt:
        style_prompt = custom_style_prompt
    else:
        style_prompt = RESPONSE_STYLES.get(
            fallback_style_id,
            RESPONSE_STYLES["concise"]
        )["prompt"]

    # --------------------------------------------------
    # Build / reuse system prompt
    # --------------------------------------------------
    if cached_system_prompt:
        system_prompt = cached_system_prompt
        return_cached_prompt = None
    else:
        system_prompt_parts = [QUESTION_DETECTION_PROMPT.strip()]
        system_prompt_parts.append("\n--- Style Rules ---\n" + style_prompt)

        # --------------------------------------------------
        # Persona + Resume + Live Interview Context
        # --------------------------------------------------
        if persona_data:
            system_prompt_parts.append("\n--- Candidate Context ---")

            if persona_data.get("position"):
                system_prompt_parts.append(
                    f"Position: {persona_data.get('position')}"
                )

            if persona_data.get("company_name"):
                system_prompt_parts.append(
                    f"Company: {persona_data.get('company_name')}"
                )

            if persona_data.get("job_description"):
                system_prompt_parts.append(
                    f"Job Description: {persona_data.get('job_description')}"
                )

            # ✅ Resume context (static, cached)
            if persona_data.get("resume_text"):
                resume_text = persona_data.get("resume_text")[:5000]
                system_prompt_parts.append("\nRESUME:\n" + resume_text)
            elif persona_data.get("resume_url"):
                system_prompt_parts.append(
                    f"Resume URL: {persona_data.get('resume_url')}"
                )

            # ✅ Live interview memory (session cache)
            if persona_data.get("live_candidate_context"):
                system_prompt_parts.append(
                    "\n--- LIVE INTERVIEW MEMORY (what the candidate has said so far) ---\n"
                    + persona_data["live_candidate_context"]
                )

        # --------------------------------------------------
        # Global answering rules
        # --------------------------------------------------
        system_prompt_parts.append(
            "\n--- Answering Rules ---\n"
            "- You ARE the candidate. Use first-person and speak as your real experience.\n"
            "- Never state you are an AI.\n"
            "- Use resume AND live interview memory where relevant.\n"
            "- Follow the response style rules above.\n"
        )

        if settings.get("programming_language"):
            system_prompt_parts.append(
                f"Preferred programming language: {settings.get('programming_language')}"
            )

        if settings.get("interviewInstructions"):
            system_prompt_parts.append(
                "Extra interview instructions: " + settings.get("interviewInstructions")
            )

        system_prompt = "\n".join(system_prompt_parts)
        return_cached_prompt = system_prompt

    # --------------------------------------------------
    # AI Call
    # --------------------------------------------------
    model = settings.get("defaultModel") or settings.get("default_model") or "gpt-4o"
    print(f"Using model: {model}")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": transcript}
    ]

    try:
        raw = await ask_ai(model, messages)
    except Exception as e:
        print(f"AI call error: {e}")
        return {
            "has_question": False,
            "question": None,
            "answer": None,
            "error": str(e),
        }

    if not raw:
        return {"has_question": False, "question": None, "answer": None}

    output = raw.strip()
    print(f"AI OUTPUT (truncated): {output[:800]}")

    if output.upper().startswith("SKIP"):
        return {
            "has_question": False,
            "question": None,
            "answer": None,
            "cached_system_prompt": return_cached_prompt,
        }

    # --------------------------------------------------
    # Parse structured output
    # --------------------------------------------------
    if "QUESTION:" in output and "ANSWER:" in output:
        try:
            q = output.split("QUESTION:", 1)[1].split("ANSWER:", 1)[0].strip()
            a = output.split("ANSWER:", 1)[1].strip()
            if not q or not a:
                q = transcript
                a = output
        except Exception:
            q = transcript
            a = output
    else:
        q = transcript
        a = output

    return {
        "has_question": True,
        "question": q,
        "answer": a,
        "cached_system_prompt": return_cached_prompt,
    }
