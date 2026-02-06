# app/ws/ws_live_interview.py
"""
OPTIMIZED - Fixed unnecessary session rebuilds
Added Mock Interview support with real-time question generation
"""

import asyncio
import json
import time
import traceback
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import OPENAI_API_KEY, RENDER_KEEPALIVE
from app.constants import ConnectionState
from app.services.transcript import TranscriptAccumulator
from app.ws.session_manager import (
    create_session,
    get_session,
    delete_session,
    log,
    SessionInitRequest,
)
from app.ws.ai_handler import run_ai_for_transcript

router = APIRouter()


@router.post("/session/init")
async def init_session(request: SessionInitRequest):
    """Session initialization endpoint"""
    return await create_session(request)


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

    await websocket.send_json({
        "type": "connection_established",
        "timestamp": time.time(),
    })

    # Connection State
    connection_state = ConnectionState.CONNECTED
    state_lock = asyncio.Lock()

    async def get_state():
        async with state_lock:
            return connection_state

    async def set_state(s):
        nonlocal connection_state
        async with state_lock:
            connection_state = s

    # Keepalive
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

    # Per-session runtime
    current_session_id: Optional[str] = None
    transcript_accumulator: Optional[TranscriptAccumulator] = None
    ai_task: Optional[asyncio.Task] = None

    send_lock = asyncio.Lock()

    async def safe_send(payload: dict):
        if await get_state() != ConnectionState.CONNECTED:
            return
        async with send_lock:
            await websocket.send_json(payload)

    # Main WS loop
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

            # Session end
            if msg_type == "session_end":
                sid = data.get("session_id")
                if sid:
                    delete_session(sid)
                continue

            # ✅ OPTIMIZED SESSION INIT - No unnecessary rebuilds
            if msg_type == "init":
                current_session_id = data.get("session_id")
                session = get_session(current_session_id)

                if not session:
                    await safe_send({"type": "error", "message": "Session not found"})
                    continue

                transcript_accumulator = session["transcript_accumulator"]

                # ✅ FIX: Only rebuild if ACTUAL changes detected
                # DON'T rebuild on every init - session already has everything!
                
                # Check if frontend sent explicit style/settings changes
                explicit_style_change = data.get("force_style_update", False)
                new_custom_prompt = data.get("custom_style_prompt")
                
                # Only rebuild if explicitly requested OR new custom prompt provided
                if explicit_style_change or (new_custom_prompt and new_custom_prompt != session.get("custom_style_prompt")):
                    log(f"🔄 Explicit settings update requested")
                    
                    if new_custom_prompt:
                        session["custom_style_prompt"] = new_custom_prompt
                    
                    # Rebuild system prompt only if really needed
                    new_settings = data.get("settings")
                    if new_settings and isinstance(new_settings, dict):
                        session["settings"].update(new_settings)
                    
                    # Re-fetch and rebuild
                    from app.supabase_client import fetch_response_style, fetch_system_default_style
                    from app.services.complete_settings import build_system_prompt_from_merged
                    
                    style_id = session["settings"].get("selected_response_style_id")
                    response_style_row = None
                    
                    if style_id:
                        try:
                            response_style_row = await asyncio.to_thread(fetch_response_style, style_id)
                        except Exception:
                            pass
                    
                    if not response_style_row:
                        try:
                            response_style_row = await asyncio.to_thread(fetch_system_default_style)
                        except Exception:
                            pass
                    
                    try:
                        new_prompt = build_system_prompt_from_merged(
                            session["settings"],
                            response_style_row,
                            session["persona_data"]
                        )
                        session["cached_system_prompt"] = new_prompt
                        
                        if response_style_row:
                            session["settings"]["responseStyleRow"] = response_style_row
                        
                        log("✅ System prompt rebuilt", "SUCCESS")
                    except Exception as e:
                        log(f"⚠️ Rebuild failed: {e}", "ERROR")
                else:
                    # ✅ NO REBUILD - Use cached session (FAST!)
                    log("✅ Using cached session (no rebuild needed)")

                await safe_send({"type": "connected", "message": "Session ready"})
                continue

            # =========================================================
            # 🎤 MOCK INTERVIEW: Request AI Question (UPDATED)
            # =========================================================
            if msg_type == "request_mock_question":
                """
                Client requests a new AI-generated interview question
                Used in mock interview mode where AI plays the interviewer
                
                ✅ UPDATED: Now uses question_number for intelligent progression
                
                Expected payload:
                {
                    "type": "request_mock_question",
                    "question_number": 1,  // ✅ NEW: determines question type/phase
                    "voice": "alloy" | "echo" | "fable" | "onyx" | "nova" | "shimmer",
                    "include_audio": true | false
                }
                
                Question progression:
                - Q1-2: Ice breakers
                - Q3-5: Behavioral 
                - Q6-8: Technical
                - Q9+: Problem solving
                """
                if not current_session_id:
                    await safe_send({"type": "error", "message": "Session not initialized"})
                    continue
                
                session = get_session(current_session_id)
                question_number = data.get("question_number", 1)  # ✅ CHANGED
                voice = data.get("voice", "alloy")
                include_audio = data.get("include_audio", True)
                
                log(f"🎯 Mock question #{question_number} requested")
                
                try:
                    from app.mock_interview import generate_question_with_voice, get_fallback_question
                    
                    # Send "generating" status
                    await safe_send({
                        "type": "mock_question_generating",
                        "question_number": question_number  # ✅ CHANGED
                    })
                    
                    # ✅ Generate question with intelligent progression
                    result = await generate_question_with_voice(
                        persona_data=session["persona_data"],
                        settings=session["settings"],
                        previous_questions=list(session["prev_questions"]),
                        question_number=question_number,  # ✅ CHANGED
                        voice=voice,
                        include_audio=include_audio
                    )
                    
                    if result:
                        # Store question in session history
                        session["prev_questions"].append(result["question"])
                        
                        # Send question to client
                        await safe_send({
                            "type": "mock_question",
                            "question": result["question"],
                            "audio": result.get("audio"),
                            "voice": result["voice"],
                            "question_number": result.get("question_number", question_number),  # ✅ CHANGED
                            "phase": result.get("phase", "unknown"),  # ✅ NEW
                            "timestamp": time.time()
                        })
                        
                        log(f"✅ Mock Q{question_number} sent: {result['question'][:50]}...", "SUCCESS")
                    else:
                        # Fallback to preset question
                        log("⚠️ AI generation failed, using fallback", "WARNING")
                        
                        fallback_q = get_fallback_question(question_number)  # ✅ CHANGED
                        
                        # Generate audio for fallback if needed
                        from app.client.openai_tts import text_to_speech_base64
                        audio = None
                        if include_audio:
                            try:
                                audio = text_to_speech_base64(text=fallback_q, voice=voice)
                                log("🔊 Fallback audio generated", "SUCCESS")
                            except Exception as audio_err:
                                log(f"⚠️ Fallback audio failed: {audio_err}", "WARNING")
                        
                        session["prev_questions"].append(fallback_q)
                        
                        # Determine phase for fallback
                        if question_number <= 2:
                            phase = "icebreaker"
                        elif question_number <= 5:
                            phase = "behavioral"
                        elif question_number <= 8:
                            phase = "technical"
                        else:
                            phase = "problem_solving"
                        
                        await safe_send({
                            "type": "mock_question",
                            "question": fallback_q,
                            "audio": audio,
                            "voice": voice,
                            "question_number": question_number,  # ✅ CHANGED
                            "phase": phase,  # ✅ NEW
                            "is_fallback": True,
                            "timestamp": time.time()
                        })
                
                except Exception as e:
                    log(f"❌ Mock question error: {e}", "ERROR")
                    await safe_send({
                        "type": "error",
                        "message": f"Failed to generate mock question: {str(e)}"
                    })
                
                continue

            # =========================================================
            # 🎤 MOCK INTERVIEW: Evaluate Answer (NEW)
            # =========================================================
            if msg_type == "evaluate_answer":
                """
                Evaluate candidate's answer to a mock interview question
                
                Expected payload:
                {
                    "type": "evaluate_answer",
                    "question": str,
                    "answer": str,
                    "get_feedback": bool (optional, default: true)
                }
                """
                if not current_session_id:
                    await safe_send({"type": "error", "message": "Session not initialized"})
                    continue
                
                question = data.get("question", "")
                answer = data.get("answer", "")
                get_feedback = data.get("get_feedback", True)
                
                if not question or not answer:
                    await safe_send({"type": "error", "message": "Question and answer required"})
                    continue
                
                log(f"📊 Evaluating answer for: {question[:50]}...")
                
                try:
                    session = get_session(current_session_id)
                    
                    if get_feedback:
                        # Generate AI feedback
                        from app.ai_router import ask_ai
                        
                        model = session["settings"].get("default_model", "gpt-4o-mini")
                        
                        feedback_prompt = f"""
You are an expert technical interviewer. Evaluate this interview answer.

QUESTION:
{question}

CANDIDATE'S ANSWER:
{answer}

Provide constructive feedback in 3-4 sentences covering:
1. What was good about the answer
2. What could be improved
3. One specific suggestion for improvement

Be encouraging but honest. Keep it concise and actionable.
"""
                        
                        messages = [
                            {"role": "system", "content": "You are a helpful interview coach providing constructive feedback."},
                            {"role": "user", "content": feedback_prompt}
                        ]
                        
                        await safe_send({"type": "feedback_generating"})
                        
                        feedback = await ask_ai(model, messages)
                        
                        await safe_send({
                            "type": "answer_feedback",
                            "question": question,
                            "answer": answer,
                            "feedback": feedback,
                            "timestamp": time.time()
                        })
                        
                        log("✅ Feedback sent", "SUCCESS")
                    else:
                        # Just acknowledge
                        await safe_send({
                            "type": "answer_acknowledged",
                            "question": question,
                            "timestamp": time.time()
                        })
                
                except Exception as e:
                    log(f"❌ Feedback error: {e}", "ERROR")
                    await safe_send({
                        "type": "error",
                        "message": f"Failed to generate feedback: {str(e)}"
                    })
                
                continue

            # Transcript trigger (EXISTING)
            if msg_type == "transcript":
                if not transcript_accumulator or not current_session_id:
                    await safe_send({"type": "error", "message": "Session not initialized"})
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

                # Cancel previous AI call
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