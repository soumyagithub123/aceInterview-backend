# app/qa.py
import asyncio
import re
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

# ✅ ULTRA-STRICT Detection prompt
QUESTION_DETECTION_PROMPT = """
You are the CANDIDATE in a real interview.

Your job:
1) Respond ONLY when the interviewer asks a REAL INTERVIEW QUESTION.
2) When you respond, produce a DETAILED, interview-ready answer.
3) Do NOT include code unless it is explicitly requested.


A) QUESTION DETECTION (Ultra-strict)

A REAL QUESTION includes:
- Personal intros (e.g., "Tell me about yourself", "Walk me through your experience")
- Experience/skills/projects/behavior/problem-solving
- Requests for explanation (e.g., "Explain...", "Describe...", "How would you...", "Why did you...")
- Coding challenges ONLY when they explicitly ask to write/implement code

ABSOLUTELY DO NOT RESPOND (return SKIP) to:
- Any statement containing "let me know if", "feel free to", "if you need"
- Encouragement: "You can do it", "You got this"
- Acknowledgments: "Okay", "Alright", "Good"
- Transitions: "Let's move on", "Next question"
- Supportive statements: "Always here to help"
- Any statement that does NOT explicitly request information or an explanation

CRITICAL EXTRACTION RULE:
When you detect a real question, extract ONLY the core question itself.
Remove ALL filler words, introductions, and pleasantries.

B) ANSWER POLICY (Detailed + No-code-by-default)

DEFAULT ANSWER STYLE:
- Detailed, structured, interview-ready (roughly 200–350 words).
- First person ("I", "my").
- Clear flow: Approach → Key decisions → Edge cases → Tradeoffs → Result/impact (if applicable).
- Use concrete examples and small details, but don’t invent metrics—only mention metrics if the user provided them.

NO-CODE RULE (Very strict):
- Do NOT include code blocks or code snippets unless the interviewer explicitly asks for code.
- Even if the topic is technical (React hooks, APIs, websockets), prefer explanation first.
- If the question is “how would you…” without “write/implement/show code”, answer conceptually with steps, patterns, and best practices.

WHEN TO INCLUDE CODE:
Include code ONLY if the question contains an explicit code request, such as:
- "write code", "implement", "show me the code", "give a snippet", "how would you code this", "can you write a component/function", "provide sample code"
If code is requested:
- Keep it minimal and relevant.
- Include brief rationale.
- No extra boilerplate.

MIXED REQUESTS:
If they ask for BOTH explanation and code:
- Give explanation first, then minimal code.

C) OUTPUT FORMAT (STRICT)
If NOT a real interview question, output EXACTLY:
SKIP

If a real question is detected, output EXACTLY:
QUESTION: <clean extracted core question only>
ANSWER: <detailed candidate answer following rules above>
"""


# ✅ POST-PROCESSING: Filter patterns that should always SKIP
SKIP_PATTERNS = [
    r"let me know if",
    r"feel free to",
    r"if you need",
    r"always here to help",
    r"here to help you",
    r"just let me know",
    r"anything else",
    r"more questions or anything",
    r"no problem.*if you need",
]


def should_skip_transcript(transcript: str) -> bool:
    """
    Post-processing filter: return True if transcript matches skip patterns
    """
    lower = transcript.lower()
    
    # Check each skip pattern
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, lower):
            print(f"🚫 SKIP FILTER: Matched pattern '{pattern}'")
            return True
    
    # Additional heuristic: if transcript is very short and has no question words
    question_words = ["what", "how", "why", "when", "where", "who", "can you", "could you", 
                      "tell me", "describe", "explain", "walk me through", "implement"]
    
    if len(transcript.split()) < 15:
        has_question_word = any(qw in lower for qw in question_words)
        if not has_question_word:
            print(f"🚫 SKIP FILTER: Short statement with no question words")
            return True
    
    return False


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

    # ✅ FIRST: Check skip patterns BEFORE calling AI
    if should_skip_transcript(transcript):
        print("⏭️ SKIPPED by pre-filter")
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
    # ✅ Parse structured output with better extraction
    # --------------------------------------------------
    if "QUESTION:" in output and "ANSWER:" in output:
        try:
            q = output.split("QUESTION:", 1)[1].split("ANSWER:", 1)[0].strip()
            a = output.split("ANSWER:", 1)[1].strip()
            
            # ✅ Validation: ensure we actually extracted something meaningful
            if not q or len(q) < 5:
                print("⚠️ Warning: Extracted question too short, using transcript")
                q = transcript
                a = output
            
            # ✅ SECOND SKIP CHECK: After extraction, verify the question isn't a skip pattern
            if should_skip_transcript(q):
                print("🚫 SKIP FILTER: Extracted question matched skip pattern")
                return {
                    "has_question": False,
                    "question": None,
                    "answer": None,
                    "cached_system_prompt": return_cached_prompt,
                }
                
        except Exception as e:
            print(f"⚠️ Warning: Failed to parse QUESTION/ANSWER format: {e}")
            q = transcript
            a = output
    else:
        # Fallback: AI didn't follow format
        print("⚠️ Warning: AI output missing QUESTION:/ANSWER: format")
        q = transcript
        a = output

    print(f"✅ EXTRACTED QUESTION: {q}")
    print(f"✅ ANSWER LENGTH: {len(a)} chars")

    return {
        "has_question": True,
        "question": q,
        "answer": a,
        "cached_system_prompt": return_cached_prompt,
    }