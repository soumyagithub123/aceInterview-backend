# app/routes/ws_live_interview.py

import asyncio
import json
import time
import traceback
from collections import deque
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import OPENAI_API_KEY, RENDER_KEEPALIVE
from app.constants import ConnectionState
from app.transcript import TranscriptAccumulator
from app.qa import process_transcript_with_ai
from app.ai_router import is_model_available
from app.complete_settings import get_complete_settings

router = APIRouter()


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


class CandidateSessionCache:
    def __init__(self, max_chars: int = 6000):
        self.full_transcript = []
        self.max_chars = max_chars

    def add(self, text: str):
        if text and text.strip():
            self.full_transcript.append(text.strip())

    def get_context(self) -> str:
        merged = " ".join(self.full_transcript)
        return merged[-self.max_chars :]


@router.websocket("/ws/live-interview")
async def websocket_live_interview(websocket: WebSocket):
    log("=" * 80)
    log("NEW WEBSOCKET CONNECTION")
    log("=" * 80)

    try:
        await websocket.accept()
        log("WebSocket accepted", "SUCCESS")
    except Exception as e:
        log(f"Failed to accept WebSocket: {e}", "ERROR")
        return

    if not OPENAI_API_KEY:
        await websocket.send_json({"type": "error", "message": "API key missing"})
        await websocket.close()
        return

    await websocket.send_json(
        {
            "type": "connection_established",
            "message": "Q&A Copilot WebSocket ready",
            "timestamp": time.time(),
        }
    )

    connection_state = ConnectionState.CONNECTED
    state_lock = asyncio.Lock()

    async def get_state():
        async with state_lock:
            return connection_state

    async def set_state(s):
        nonlocal connection_state
        async with state_lock:
            connection_state = s

    should_keepalive = True
    keepalive_task: Optional[asyncio.Task] = None

    async def send_keepalive():
        try:
            while should_keepalive and await get_state() == ConnectionState.CONNECTED:
                await asyncio.sleep(RENDER_KEEPALIVE)
                try:
                    await websocket.send_json({"type": "ping", "timestamp": time.time()})
                except Exception as e:
                    log(f"Keepalive failed: {e}", "ERROR")
                    await set_state(ConnectionState.DISCONNECTING)
                    break
        except asyncio.CancelledError:
            pass

    transcript_accumulator: Optional[TranscriptAccumulator] = None
    prev_questions = deque(maxlen=10)
    send_lock = asyncio.Lock()

    merged = None
    settings = None
    persona_data = None
    cached_system_prompt = None
    custom_style_prompt = None

    candidate_cache = CandidateSessionCache()

    ai_task: Optional[asyncio.Task] = None
    current_req_id: Optional[str] = None

    async def safe_send(payload: dict) -> bool:
        if await get_state() != ConnectionState.CONNECTED:
            return False
        try:
            async with send_lock:
                await websocket.send_json(payload)
            return True
        except Exception as e:
            log(f"Send error: {e}", "ERROR")
            try:
                await set_state(ConnectionState.DISCONNECTING)
            except Exception:
                pass
            return False

    await safe_send({"type": "ready", "message": "Q&A ready"})
    keepalive_task = asyncio.create_task(send_keepalive())
    log("Ready message sent, keepalive started", "SUCCESS")

    async def run_ai_for_transcript(clean: str, req_id: str):
        nonlocal cached_system_prompt

        if settings is None:
            return

        persona_with_context = dict(persona_data or {})
        persona_with_context["live_candidate_context"] = candidate_cache.get_context()

        await safe_send({"type": "answer_start", "id": req_id, "timestamp": time.time()})

        try:
            stream_obj = process_transcript_with_ai(
                clean,
                settings,
                persona_with_context,
                custom_style_prompt,
                cached_system_prompt,
                stream=True,
            )
        except TypeError:
            stream_obj = None

        # Streaming path
        if stream_obj is not None and hasattr(stream_obj, "__aiter__"):
            final = None
            try:
                async for ev in stream_obj:
                    if asyncio.current_task().cancelled():
                        raise asyncio.CancelledError

                    et = (ev or {}).get("type")

                    if et == "question":
                        q = (ev or {}).get("question") or ""
                        if not q.strip():
                            continue
                        if any(q.lower() == prev.lower() for prev in prev_questions):
                            log("Duplicate question - skipping", "WARNING")
                            return
                        prev_questions.append(q)
                        await safe_send({"type": "question_detected", "id": req_id, "question": q})

                    elif et == "delta":
                        d = (ev or {}).get("delta") or ""
                        if d:
                            await safe_send({"type": "answer_delta", "id": req_id, "delta": d})

                    elif et == "done":
                        final = ev
                        break

                    elif et == "error":
                        await safe_send({"type": "error", "message": (ev or {}).get("message", "AI error")})
                        return

            except asyncio.CancelledError:
                await safe_send({"type": "answer_cancelled", "id": req_id})
                return
            except Exception as e:
                log(f"AI streaming error: {e}", "ERROR")
                await safe_send({"type": "error", "message": str(e)})
                return

            if not final:
                return

            new_prompt = final.get("cached_system_prompt")
            if new_prompt and not cached_system_prompt:
                cached_system_prompt = new_prompt
                log("System prompt cached for session", "SUCCESS")

            if final.get("has_question"):
                q = final.get("question") or ""
                a = final.get("answer") or ""
                if q and not any(q.lower() == prev.lower() for prev in prev_questions):
                    prev_questions.append(q)
                    await safe_send({"type": "question_detected", "id": req_id, "question": q})

                # Backward-compatible final payload
                await safe_send({"type": "answer_ready", "id": req_id, "question": q, "answer": a})
                log("Answer sent", "SUCCESS")
            return

        # Fallback: non-stream (kept for safety)
        try:
            result = await asyncio.wait_for(
                process_transcript_with_ai(
                    clean,
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

        new_prompt = result.get("cached_system_prompt")
        if new_prompt and not cached_system_prompt:
            cached_system_prompt = new_prompt
            log("System prompt cached for session", "SUCCESS")

        if result.get("has_question"):
            q = result.get("question") or ""
            a = result.get("answer") or ""

            if any(q.lower() == prev.lower() for prev in prev_questions):
                log("Duplicate question - skipping", "WARNING")
                return

            prev_questions.append(q)
            await safe_send({"type": "question_detected", "id": req_id, "question": q})
            await safe_send({"type": "answer_ready", "id": req_id, "question": q, "answer": a})
            log("Answer sent", "SUCCESS")

    try:
        while await get_state() == ConnectionState.CONNECTED:
            try:
                raw_msg = await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                log("Client disconnected", "WARNING")
                break

            try:
                data = json.loads(raw_msg)
            except Exception:
                await safe_send({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = data.get("type", "")
            log(f"Received: {msg_type}", "DEBUG")

            if msg_type == "client_ready":
                await safe_send(
                    {
                        "type": "server_ack",
                        "message": "Handshake confirmed",
                        "server_time": time.time(),
                    }
                )
                continue

            if msg_type == "pong":
                continue

            if msg_type == "init":
                user_id = data.get("user_id")
                persona_id = data.get("persona_id") or data.get("personaId")
                resume_path = data.get("resume_path")

                log(f"INIT for user={user_id} persona={persona_id}", "INFO")

                try:
                    merged = await get_complete_settings(user_id, persona_id, resume_path)
                    settings = merged.get("settings", {})
                    settings["responseStyleRow"] = merged.get("response_style") or {}
                    persona_data = merged.get("persona") or {"resume_url": None, "resume_text": None}
                    cached_system_prompt = merged.get("system_prompt")
                except Exception as e:
                    log(f"Error building complete settings: {e}", "ERROR")
                    settings = None

                model = settings.get("default_model") if settings else None
                if model and not is_model_available(model):
                    await safe_send({"type": "error", "message": f"Model {model} not available"})

                # ✅ pause_interval stays here (2s default). DO NOT sleep again later.
                transcript_accumulator = TranscriptAccumulator(
                    pause_threshold=float(settings.get("pause_interval", 2))
                )

                await safe_send({"type": "connected", "message": "Q&A initialized"})
                continue

            if msg_type == "transcript":
                if not transcript_accumulator or settings is None:
                    await safe_send({"type": "error", "message": "Session not initialized"})
                    continue

                transcript = data.get("transcript", "")
                is_final = data.get("is_final", False)
                speech_final = data.get("speech_final", False)

                complete = transcript_accumulator.add_transcript(transcript, is_final, speech_final)
                if not complete:
                    continue

                clean = complete.strip()
                log(f"Complete transcript: {clean[:120]}...", "INFO")
                candidate_cache.add(clean)

                # Cancel any in-flight generation and start latest (prevents backlog)
                if ai_task and not ai_task.done():
                    ai_task.cancel()

                current_req_id = str(uuid4())
                ai_task = asyncio.create_task(run_ai_for_transcript(clean, current_req_id))
                continue

    except Exception as e:
        log(f"Fatal WebSocket error: {e}", "ERROR")
        traceback.print_exc()

    finally:
        log("Cleaning up", "INFO")
        should_keepalive = False

        try:
            await set_state(ConnectionState.DISCONNECTED)
        except Exception:
            pass

        if ai_task and not ai_task.done():
            ai_task.cancel()
            try:
                await ai_task
            except Exception:
                pass

        if keepalive_task:
            keepalive_task.cancel()
            try:
                await keepalive_task
            except Exception:
                pass

        try:
            await websocket.close()
        except Exception:
            pass

        log("=" * 80)
        log("WEBSOCKET CLOSED")
        log("=" * 80)
