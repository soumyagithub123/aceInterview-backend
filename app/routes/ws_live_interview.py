import asyncio
import json
import time
from collections import deque  # FIX: added missing import

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import OPENAI_API_KEY, DEFAULT_MODEL, RENDER_KEEPALIVE
from app.constants import ConnectionState
from app.transcript import TranscriptAccumulator
from app.qa import process_transcript_with_ai

router = APIRouter()

@router.websocket("/ws/live-interview")
async def websocket_live_interview(websocket: WebSocket):
    await websocket.accept()
    if not OPENAI_API_KEY:
        await websocket.send_json({
            "type": "error",
            "message": "OPENAI_API_KEY not configured on server. Set in Render Dashboard."
        })
        await websocket.close()
        return

    await websocket.send_json({
        "type": "connection_established",
        "message": "Q&A WebSocket ready",
        "timestamp": time.time()
    })

    print("\n🤖 Q&A Copilot connected")

    connection_state = ConnectionState.CONNECTED
    state_lock = asyncio.Lock()

    keepalive_task = None
    should_keepalive = True

    async def get_state():
        async with state_lock:
            return connection_state

    async def set_state(new_state: ConnectionState):
        nonlocal connection_state
        async with state_lock:
            connection_state = new_state

    async def send_render_keepalive():
        try:
            while should_keepalive and await get_state() == ConnectionState.CONNECTED:
                await asyncio.sleep(RENDER_KEEPALIVE)
                if await get_state() == ConnectionState.CONNECTED:
                    await websocket.send_json({
                        "type": "keepalive",
                        "timestamp": time.time()
                    })
        except asyncio.CancelledError:
            pass

    transcript_accumulator = None
    prev_questions = deque(maxlen=10)
    processing_lock = asyncio.Lock()
    send_lock = asyncio.Lock()

    settings = {
        "audioLanguage": "English",
        "pauseInterval": 2.0,
        "advancedQuestionDetection": False,
        "selectedResponseStyleId": "concise",
        "programmingLanguage": "Python",
        "interviewInstructions": "",
        "defaultModel": DEFAULT_MODEL,
        "messageDirection": "bottom",
        "autoScroll": True
    }

    persona_data = None
    custom_style_prompt = None

    async def safe_send(data: dict) -> bool:
        if await get_state() != ConnectionState.CONNECTED:
            return False
        try:
            async with send_lock:
                await websocket.send_json(data)
            return True
        except Exception:
            await set_state(ConnectionState.DISCONNECTING)
            return False

    try:
        await safe_send({"type": "ready", "message": "Q&A ready"})
        keepalive_task = asyncio.create_task(send_render_keepalive())

        while await get_state() == ConnectionState.CONNECTED:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
                data = json.loads(message)

                if data.get("type") == "client_ready":
                    await safe_send({"type": "server_ack", "message": "Handshake confirmed", "server_time": time.time()})
                    continue
                elif data.get("type") == "pong":
                    continue
                elif data.get("type") == "init":
                    received_settings = data.get("settings", {})
                    settings.update(received_settings)

                    transcript_accumulator = TranscriptAccumulator(pause_threshold=settings.get("pauseInterval", 2.0))

                    persona_data = {
                        "position": data.get("position", ""),
                        "company_name": data.get("company_name", ""),
                        "company_description": data.get("company_description", ""),
                        "job_description": data.get("job_description", ""),
                        "resume_text": data.get("resume_text", ""),
                        "resume_filename": data.get("resume_filename", "")
                    }
                    custom_style_prompt = data.get("custom_style_prompt", None)

                    print("=" * 60)
                    print("🎯 Q&A INITIALIZED")
                    print("=" * 60)

                    await safe_send({"type": "connected", "message": "Q&A initialized"})

                elif data.get("type") == "transcript":
                    if not transcript_accumulator:
                        print("⚠ No transcript accumulator - Q&A not initialized")
                        continue
                    transcript = data.get("transcript", "")
                    is_final = data.get("is_final", False)
                    speech_final = data.get("speech_final", False)

                    print(f"📝 Received transcript: {transcript[:100]}... (final={is_final}, speech_final={speech_final})")

                    complete_paragraph = transcript_accumulator.add_transcript(transcript, is_final, speech_final)

                    if complete_paragraph:
                        print(f"📋 Complete paragraph detected: {complete_paragraph[:100]}...")

                        if processing_lock.locked():
                            print("⏳ Already processing, skipping...")
                            continue

                        async with processing_lock:
                            if any(complete_paragraph.lower() == prev.lower() for prev in prev_questions):
                                continue

                            print(f"🔍 Processing: {complete_paragraph[:100]}...")

                            result = await process_transcript_with_ai(
                                complete_paragraph,
                                settings,
                                persona_data,
                                custom_style_prompt
                            )

                            print(f"📊 Result: has_question={result['has_question']}, question={result.get('question', 'None')[:50] if result.get('question') else 'None'}...")

                            if result["has_question"]:
                                prev_questions.append(complete_paragraph)

                                print(f"✅ Sending question: {result['question'][:100]}...")
                                await safe_send({
                                    "type": "question_detected",
                                    "question": result["question"]
                                })

                                await asyncio.sleep(0.1)

                                print(f"✅ Sending answer: {result['answer'][:100]}...")
                                await safe_send({
                                    "type": "answer_ready",
                                    "question": result["question"],
                                    "answer": result["answer"]
                                })
                                print("✅ Q&A sent successfully")

            except asyncio.TimeoutError:
                continue

    except WebSocketDisconnect:
        print("❌ Q&A disconnected")
    except Exception as e:
        print(f"❌ Q&A error: {e}")
    finally:
        should_keepalive = False
        await set_state(ConnectionState.DISCONNECTED)
        if keepalive_task:
            keepalive_task.cancel()
        try:
            await websocket.close()
        except:
            pass
        print("🔌 Q&A closed\n")