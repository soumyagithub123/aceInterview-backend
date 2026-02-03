import asyncio
import json
import time
import traceback
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import OPENAI_API_KEY, RENDER_KEEPALIVE
from app.constants import ConnectionState
from app.transcript import TranscriptAccumulator
from app.ws.session_manager import (
    create_session,
    get_session,
    delete_session,
    log,
    SessionInitRequest,
)
from app.ws.ai_handler import run_ai_for_transcript
from app.supabase_client import fetch_response_style, fetch_system_default_style
from app.complete_settings import build_system_prompt_from_merged

router = APIRouter()


@router.post("/session/init")
async def init_session(request: SessionInitRequest):
    """
    Thin wrapper → real logic in session_manager
    """
    return await create_session(request)


# =========================================================
# LIVE INTERVIEW WEBSOCKET (THIN)
# =========================================================
@router.websocket("/ws/live-interview")
async def websocket_live_interview(websocket: WebSocket):
    log("=" * 80)
    log("NEW WEBSOCKET CONNECTION")
    log("=" * 80)

    await websocket.accept()

    if not OPENAI_API_KEY:
        await websocket.send_json({"type": "error", "message": "API key missing"})
        await websocket.close()
        return

    await websocket.send_json(
        {
            "type": "connection_established",
            "timestamp": time.time(),
        }
    )

    # -----------------------------
    # Connection State
    # -----------------------------
    connection_state = ConnectionState.CONNECTED
    state_lock = asyncio.Lock()

    async def get_state():
        async with state_lock:
            return connection_state

    async def set_state(s):
        nonlocal connection_state
        async with state_lock:
            connection_state = s

    # -----------------------------
    # Keepalive
    # -----------------------------
    should_keepalive = True

    async def send_keepalive():
        try:
            while should_keepalive and await get_state() == ConnectionState.CONNECTED:
                await asyncio.sleep(RENDER_KEEPALIVE)
                await websocket.send_json({"type": "ping", "ts": time.time()})
        except asyncio.CancelledError:
            pass
        except Exception:
            await set_state(ConnectionState.DISCONNECTING)

    keepalive_task = asyncio.create_task(send_keepalive())

    # -----------------------------
    # Per-session runtime
    # -----------------------------
    current_session_id: Optional[str] = None
    transcript_accumulator: Optional[TranscriptAccumulator] = None
    ai_task: Optional[asyncio.Task] = None

    send_lock = asyncio.Lock()

    async def safe_send(payload: dict):
        if await get_state() != ConnectionState.CONNECTED:
            return
        async with send_lock:
            await websocket.send_json(payload)

    # -----------------------------
    # Main WS loop
    # -----------------------------
    try:
        while await get_state() == ConnectionState.CONNECTED:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                break

            data = json.loads(raw)
            msg_type = data.get("type")

            # -------------------------
            # Session end
            # -------------------------
            if msg_type == "session_end":
                sid = data.get("session_id")
                if sid:
                    delete_session(sid)
                continue

            # -------------------------
            # Session init / resume
            # -------------------------
            if msg_type == "init":
                current_session_id = data.get("session_id")
                session = get_session(current_session_id)

                if not session:
                    await safe_send(
                        {"type": "error", "message": "Session not found"}
                    )
                    continue

                transcript_accumulator = session["transcript_accumulator"]

                # -------------------------------------------------
                # ✅ DYNAMIC SETTINGS UPDATE (Style Change Fix)
                # -------------------------------------------------
                new_settings = data.get("settings")
                # Also check for direct prompt overrides
                custom_style_prompt = data.get("custom_style_prompt")

                if new_settings or custom_style_prompt:
                    log(f"🔄 Updating session settings/style...")
                    
                    if new_settings and isinstance(new_settings, dict):
                        session["settings"].update(new_settings)
                        # Ensure we capture the selected ID
                        new_style_id = new_settings.get("selectedResponseStyleId")
                        if new_style_id:
                            session["settings"]["selected_response_style_id"] = new_style_id
                    
                    if custom_style_prompt:
                         session["custom_style_prompt"] = custom_style_prompt

                    # Re-fetch style row if ID is present (to be safe)
                    style_id = session["settings"].get("selected_response_style_id")
                    response_style_row = None
                    if style_id:
                         try:
                            response_style_row = await asyncio.to_thread(fetch_response_style, style_id)
                         except Exception:
                            pass
                    
                    if not response_style_row:
                        # Fallback to system default
                         try:
                            response_style_row = await asyncio.to_thread(fetch_system_default_style)
                         except Exception:
                            pass

                    # FORCE Rebuild System Prompt
                    try:
                        new_prompt = build_system_prompt_from_merged(
                            session["settings"],
                            response_style_row,
                            session["persona_data"]
                        )
                        session["cached_system_prompt"] = new_prompt
                        # Also update the row in session settings for good measure
                        if response_style_row:
                             session["settings"]["responseStyleRow"] = response_style_row
                        
                        log("✅ System prompt rebuilt with updated settings", "SUCCESS")
                    except Exception as e:
                        log(f"⚠️ Failed to rebuild prompt: {e}", "ERROR")

                await safe_send(
                    {"type": "connected", "message": "Session ready"}
                )
                continue

            # -------------------------
            # Transcript trigger
            # -------------------------
            if msg_type == "transcript":
                if not transcript_accumulator or not current_session_id:
                    await safe_send(
                        {"type": "error", "message": "Session not initialized"}
                    )
                    continue

                transcript = data.get("transcript", "")
                is_final = data.get("is_final", False)
                speech_final = data.get("speech_final", False)

                completed = transcript_accumulator.add_transcript(
                    transcript, is_final, speech_final
                )

                if not completed:
                    continue

                clean = completed.strip()
                session = get_session(current_session_id)

                # cancel previous AI call
                if ai_task and not ai_task.done():
                    ai_task.cancel()

                ai_task = asyncio.create_task(
                    run_ai_for_transcript(
                        clean_transcript=clean,
                        settings=session["settings"],
                        persona_data=session["persona_data"],
                        candidate_cache=session["candidate_cache"],
                        prev_questions=session["prev_questions"],
                        custom_style_prompt=session["custom_style_prompt"],
                        cached_system_prompt=session["cached_system_prompt"],
                        safe_send=safe_send,
                        session_id=current_session_id,
                    )
                )

    except Exception as e:
        log(f"Fatal WS error: {e}", "ERROR")
        traceback.print_exc()

    finally:
        should_keepalive = False
        keepalive_task.cancel()

        if ai_task and not ai_task.done():
            ai_task.cancel()

        try:
            await websocket.close()
        except Exception:
            pass

        await set_state(ConnectionState.DISCONNECTED)

        log("=" * 80)
        log("WEBSOCKET CLOSED")
        log("=" * 80)
