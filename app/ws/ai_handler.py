import asyncio
import time
from typing import Optional, Dict, Any
from uuid import uuid4

from app.qa import process_transcript_with_ai
from app.ws.session_manager import log


# =========================================================
# AI EXECUTOR (Prompt-2 owner)
# =========================================================
async def run_ai_for_transcript(
    *,
    clean_transcript: str,
    settings: Dict[str, Any],
    persona_data: Dict[str, Any],
    candidate_cache,
    prev_questions,
    custom_style_prompt: Optional[str],
    cached_system_prompt: Optional[str],
    safe_send,
    session_id: Optional[str] = None,
):
    """
    Executes AI for a finalized transcript.
    Handles:
    - streaming
    - fallback
    - question detection
    - answer events
    """

    req_id = str(uuid4())

    persona_with_context = dict(persona_data or {})
    persona_with_context["live_candidate_context"] = (
        candidate_cache.get_context() if candidate_cache else ""
    )

    await safe_send(
        {
            "type": "answer_start",
            "id": req_id,
            "timestamp": time.time(),
        }
    )

    # --------------------------------------------------
    # STREAMING PATH (PRIMARY)
    # --------------------------------------------------
    try:
        stream_obj = process_transcript_with_ai(
            clean_transcript,
            settings,
            persona_with_context,
            custom_style_prompt,
            cached_system_prompt,
            stream=True,
        )
    except TypeError:
        stream_obj = None

    if stream_obj is not None and hasattr(stream_obj, "__aiter__"):
        final = None

        try:
            async for ev in stream_obj:
                et = (ev or {}).get("type")

                if et == "question":
                    q = ev.get("question", "").strip()
                    if not q:
                        continue

                    prev_questions.append(q)
                    await safe_send(
                        {
                            "type": "question_detected",
                            "id": req_id,
                            "question": q,
                        }
                    )

                elif et == "delta":
                    d = ev.get("delta", "")
                    if d:
                        await safe_send(
                            {
                                "type": "answer_delta",
                                "id": req_id,
                                "delta": d,
                            }
                        )

                elif et == "done":
                    final = ev
                    break

                elif et == "error":
                    await safe_send(
                        {
                            "type": "error",
                            "message": ev.get("message", "AI error"),
                        }
                    )
                    return

        except asyncio.CancelledError:
            await safe_send(
                {
                    "type": "answer_cancelled",
                    "id": req_id,
                }
            )
            return

        except Exception as e:
            log(f"AI streaming error: {e}", "ERROR")
            await safe_send(
                {"type": "error", "message": str(e)}
            )
            return

        if not final:
            return

        # -----------------------------
        # FINAL RESULT (STREAM)
        # -----------------------------
        if final.get("has_question"):
            q = final.get("question", "")
            a = final.get("answer", "")

            if q and not any(q.lower() == p.lower() for p in prev_questions):
                prev_questions.append(q)
                await safe_send(
                    {
                        "type": "question_detected",
                        "id": req_id,
                        "question": q,
                    }
                )

            await safe_send(
                {
                    "type": "answer_ready",
                    "id": req_id,
                    "question": q,
                    "answer": a,
                }
            )

            log("Answer sent (stream)", "SUCCESS")

        return final

    # --------------------------------------------------
    # FALLBACK NON-STREAM (SAFETY)
    # --------------------------------------------------
    try:
        result = await asyncio.wait_for(
            process_transcript_with_ai(
                clean_transcript,
                settings,
                persona_with_context,
                custom_style_prompt,
                cached_system_prompt,
            ),
            timeout=30,
        )
    except asyncio.TimeoutError:
        await safe_send({"type": "error", "message": "AI timeout"})
        return
    except asyncio.CancelledError:
        await safe_send({"type": "answer_cancelled", "id": req_id})
        return
    except Exception as e:
        log(f"AI pipeline error: {e}", "ERROR")
        await safe_send({"type": "error", "message": str(e)})
        return

    if result.get("has_question"):
        q = result.get("question", "")
        a = result.get("answer", "")

        if any(q.lower() == p.lower() for p in prev_questions):
            log("Duplicate question skipped", "WARNING")
            return

        prev_questions.append(q)
        await safe_send(
            {"type": "question_detected", "id": req_id, "question": q}
        )
        await safe_send(
            {"type": "answer_ready", "id": req_id, "question": q, "answer": a}
        )

        log("Answer sent (fallback)", "SUCCESS")

    return result
