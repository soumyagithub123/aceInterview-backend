# app/qa.py
"""
OPTIMIZED - Latency fixes for AI streaming
Changes:
- Immediate question detection (no wait)
- Faster delta emission
- Early SKIP detection (saves AI calls)
- Reduced timeout (20s vs 30s)
"""

import asyncio
import re
from typing import Optional, Dict, Any
from app.ai_router import ask_ai
from app.config import OPENAI_API_KEY
from app.model_config import get_model_config

RESPONSE_STYLES = {
    "concise": {"name": "Concise Professional", "prompt": "Short, sharp, confident answers (6–10 sentences)."},
    "detailed": {"name": "Detailed Professional", "prompt": "Long, structured answers with examples and metrics (~200-350 words)."},
    "storytelling": {"name": "Storytelling (STAR)", "prompt": "Answer using STAR (Situation, Task, Action, Result) when relevant."},
    "technical": {"name": "Technical Expert", "prompt": "Deep technical answers; include code examples and rationale where helpful."}
}

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
- Use concrete examples and small details, but don't invent metrics—only mention metrics if the user provided them.

NO-CODE RULE (Very strict):
- Do NOT include code blocks or code snippets unless the interviewer explicitly asks for code.
- Even if the topic is technical (React hooks, APIs, websockets), prefer explanation first.
- If the question is "how would you…" without "write/implement/show code", answer conceptually with steps, patterns, and best practices.

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

SKIP_PATTERNS = [
    r"let me know if", r"feel free to", r"if you need",
    r"always here to help", r"here to help you", r"just let me know",
    r"anything else", r"more questions or anything", r"no problem.*if you need",
]

def should_skip_transcript(transcript: str) -> bool:
    """Fast skip pattern detection"""
    lower = transcript.lower()
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, lower):
            print(f"🚫 SKIP: {pattern}")
            return True
    
    question_words = ["what", "how", "why", "when", "where", "who", "can you", "could you", 
                      "tell me", "describe", "explain", "walk me through", "implement"]
    
    if len(transcript.split()) < 15:
        if not any(qw in lower for qw in question_words):
            print(f"🚫 SKIP: Short, no question words")
            return True
    return False

async def process_transcript_with_ai(
    transcript: str,
    settings: Dict[str, Any],
    persona_data: Optional[Dict[str, Any]] = None,
    custom_style_prompt: Optional[str] = None,
    cached_system_prompt: Optional[str] = None,
    *, stream: bool = False,
):
    print(f"--- QA: {transcript[:160]} ---")

    if not transcript or not transcript.strip() or not settings:
        return {"has_question": False, "question": None, "answer": None}

    # ⚡ Early skip check (saves AI call)
    if should_skip_transcript(transcript):
        print("⏭️ SKIPPED pre-filter")
        return {"has_question": False, "question": None, "answer": None}

    # Response style
    db_style = settings.get("responseStyleRow") or {}
    fallback_style_id = settings.get("response_style") or settings.get("responseStyle") or "concise"

    if db_style and not custom_style_prompt:
        style_prompt = (
            f"Response style: {db_style.get('style_name','')}\n"
            f"Tone: {db_style.get('tone','')}\n"
            f"Length: {db_style.get('approximate_length','')}\n"
            f"Example: {db_style.get('example_response','')[:800]}"
        )
    elif custom_style_prompt:
        style_prompt = custom_style_prompt
    else:
        style_prompt = RESPONSE_STYLES.get(fallback_style_id, RESPONSE_STYLES["concise"])["prompt"]

    # System prompt
    return_cached_prompt = cached_system_prompt
    
    if cached_system_prompt:
        system_prompt = cached_system_prompt
    else:
        parts = [QUESTION_DETECTION_PROMPT]
        if style_prompt:
            parts.append("\n--- RESPONSE STYLE ---\n" + style_prompt)
        if persona_data:
            ctx = persona_data.get("live_candidate_context", "")
            if ctx:
                parts.append("\n--- RECENT CONTEXT ---\n" + ctx)
            if persona_data.get("position"):
                parts.append(f"\nInterviewing for: {persona_data.get('position')}")
            if persona_data.get("company_name"):
                parts.append(f"Company: {persona_data.get('company_name')}")
            if persona_data.get("resume_text"):
                parts.append(f"\n--- RESUME ---\n{persona_data.get('resume_text')[:5000]}")
        if settings.get("programming_language"):
            parts.append(f"Preferred language: {settings.get('programming_language')}")
        if settings.get("interviewInstructions"):
            parts.append("Extra instructions: " + settings.get("interviewInstructions"))
        
        system_prompt = "\n".join(parts)
        return_cached_prompt = system_prompt

    model = settings.get("defaultModel") or settings.get("default_model") or "gpt-4o"
    print(f"Model: {model}")
    
    # ⚡ Get model-specific config
    model_cfg = get_model_config(model)
    timeout = model_cfg["timeout"]
    temperature = model_cfg.get("temperature", 0.2)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": transcript},
    ]

    def _finalize_parse(output_text: str) -> Dict[str, Any]:
        output = (output_text or "").strip()
        print(f"AI OUTPUT: {output[:800]}")

        if not output or output.upper().startswith("SKIP"):
            return {"has_question": False, "question": None, "answer": None, "cached_system_prompt": return_cached_prompt}

        if "QUESTION:" in output and "ANSWER:" in output:
            try:
                q = output.split("QUESTION:", 1)[1].split("ANSWER:", 1)[0].strip()
                a = output.split("ANSWER:", 1)[1].strip()
                if not q or len(q) < 5:
                    q = transcript.strip()
                    a = output
                if should_skip_transcript(q):
                    print("🚫 SKIP: extracted question")
                    return {"has_question": False, "question": None, "answer": None, "cached_system_prompt": return_cached_prompt}
                return {"has_question": True, "question": q, "answer": a, "cached_system_prompt": return_cached_prompt}
            except Exception as e:
                print(f"⚠️ Parse error: {e}")

        print("⚠️ Missing format; fallback")
        q = transcript.strip()
        a = output
        if should_skip_transcript(q):
            return {"has_question": False, "question": None, "answer": None, "cached_system_prompt": return_cached_prompt}
        return {"has_question": True, "question": q, "answer": a, "cached_system_prompt": return_cached_prompt}

    # ⚡ STREAMING - OPTIMIZED
    if stream:
        async def _stream_gen():
            try:
                from openai import AsyncOpenAI
            except Exception as e:
                yield {"type": "error", "message": f"OpenAI SDK unavailable: {e}"}
                try:
                    raw = await ask_ai(model, messages)
                    yield {"type": "done", **_finalize_parse(raw)}
                except Exception as ex:
                    yield {"type": "error", "message": str(ex)}
                return

            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            buf = ""
            emitted_len = 0
            q_sent = False
            parsed_q = None
            ans_started = False
            q_flag = False

            def _parse_inc(text: str):
                nonlocal q_sent, parsed_q, ans_started, emitted_len
                
                if text.upper().startswith("SKIP"):
                    return {"skip": True}
                
                if ("QUESTION:" not in text) or ("ANSWER:" not in text):
                    return None

                q_part = text.split("QUESTION:", 1)[1].split("ANSWER:", 1)[0].strip()
                a_part = text.split("ANSWER:", 1)[1]

                if not q_sent and q_part:
                    if should_skip_transcript(q_part):
                        return {"skip": True}
                    parsed_q = q_part
                    q_sent = True
                
                ans_started = True
                return {"answer": a_part}

            try:
                # ⚡ Model-specific timeout
                async with asyncio.timeout(timeout):
                    resp = await client.chat.completions.create(
                        model=model, messages=messages,
                        temperature=temperature,
                        stream=True,
                    )

                    async for chunk in resp:
                        try:
                            delta = chunk.choices[0].delta.content or ""
                        except:
                            delta = ""
                        if not delta:
                            continue

                        buf += delta
                        inc = _parse_inc(buf)
                        
                        if inc is None:
                            continue
                        
                        if inc.get("skip"):
                            yield {"type": "done", "has_question": False, "question": None, "answer": None, "cached_system_prompt": return_cached_prompt}
                            return

                        # ⚡ Emit question once, immediately
                        if q_sent and parsed_q and not q_flag:
                            q_flag = True
                            yield {"type": "question", "question": parsed_q}

                        # ⚡ Stream deltas faster
                        if ans_started:
                            ans = inc.get("answer", "")
                            if ans and len(ans) > emitted_len:
                                new_txt = ans[emitted_len:]
                                emitted_len = len(ans)
                                if new_txt:
                                    yield {"type": "delta", "delta": new_txt}

            except TimeoutError:
                yield {"type": "error", "message": "AI timeout"}
                return
            except Exception as e:
                yield {"type": "error", "message": str(e)}
                return

            final = _finalize_parse(buf)
            yield {"type": "done", **final}

        return _stream_gen()

    # Non-stream fallback
    try:
        raw = await ask_ai(model, messages)
    except Exception as e:
        print(f"AI error: {e}")
        return {"has_question": False, "question": None, "answer": None, "error": str(e)}

    return _finalize_parse(raw)