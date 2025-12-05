import asyncio
import json
import time
from fastapi import APIRouter, WebSocket
from app.config import DEEPGRAM_API_KEY, RENDER_KEEPALIVE
from app.deepgram import DualStreamManager, ConnectionState

router = APIRouter()

@router.websocket("/ws/dual-transcribe")
async def websocket_dual_transcribe(websocket: WebSocket):
    await websocket.accept()
    if not DEEPGRAM_API_KEY:
        await websocket.send_json({
            "type": "error",
            "message": "DEEPGRAM_API_KEY not configured on server. Set in Render Dashboard."
        })
        await websocket.close()
        return

    await websocket.send_json({
        "type": "connection_established",
        "message": "Deepgram WebSocket ready",
        "timestamp": time.time()
    })

    print("\n🎙️ Deepgram connected")

    language = websocket.query_params.get("language", "en")
    stream_manager = DualStreamManager(DEEPGRAM_API_KEY, language)

    should_keepalive = True
    keepalive_task = None

    async def send_render_keepalive():
        try:
            while should_keepalive:
                await asyncio.sleep(RENDER_KEEPALIVE)
                if should_keepalive:
                    try:
                        await websocket.send_json({
                            "type": "keepalive",
                            "timestamp": time.time()
                        })
                        print(f"🏓 Deepgram keepalive sent")
                    except Exception as e:
                        print(f"❌ Keepalive failed: {e}")
                        break
        except asyncio.CancelledError:
            print("⏹️ Deepgram keepalive cancelled")

    try:
        await websocket.send_json({"type": "ready", "message": "Deepgram ready"})
        await stream_manager.connect_all()

        keepalive_task = asyncio.create_task(send_render_keepalive())
        await websocket.send_json({"type": "connected", "message": "Deepgram streams ready"})

        async def handle_audio():
            try:
                while stream_manager.is_active:
                    try:
                        message = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                    except asyncio.TimeoutError:
                        continue

                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError as e:
                        print(f"❌ Invalid JSON received: {e}")
                        continue

                    try:
                        msg_type = data.get("type")
                        if msg_type == "client_ready":
                            await websocket.send_json({
                                "type": "server_ack",
                                "message": "Handshake confirmed",
                                "server_time": time.time()
                            })
                            continue
                        elif msg_type == "pong":
                            continue

                        stream_type = msg_type
                        audio_data = data.get("audio")
                        if not audio_data or not stream_type:
                            continue

                        if isinstance(audio_data, list):
                            import struct
                            audio_bytes = struct.pack(f'{len(audio_data)}h', *audio_data)
                        elif isinstance(audio_data, str):
                            import base64
                            audio_bytes = base64.b64decode(audio_data)
                        else:
                            audio_bytes = audio_data

                        if stream_type == "candidate":
                            await stream_manager.candidate_stream.send_audio(audio_bytes)
                        elif stream_type == "interviewer":
                            await stream_manager.interviewer_stream.send_audio(audio_bytes)

                    except Exception as e:
                        print(f"❌ Audio processing error: {e}")
                        continue

            except Exception as e:
                print(f"❌ Unexpected audio handler error: {e}")

        async def handle_transcripts():
            async def process_stream(stream):
                try:
                    while stream_manager.is_active and stream.state == ConnectionState.CONNECTED:
                        transcript_data = await stream.receive_transcripts()
                        if not transcript_data:
                            await asyncio.sleep(0.01)
                            continue
                        
                        # 🔥 KEY CHANGE: Handle BOTH interim and final results
                        if transcript_data.get("type") == "Results":
                            channel = transcript_data.get("channel", {})
                            alternatives = channel.get("alternatives", [])
                            if alternatives and len(alternatives) > 0:
                                transcript = alternatives[0].get("transcript", "")
                                if transcript.strip():
                                    # Send ALL transcripts (interim AND final)
                                    response = {
                                        "type": "transcript",
                                        "stream": stream.stream_type.value,
                                        "transcript": transcript,
                                        "is_final": transcript_data.get("is_final", False),
                                        "speech_final": transcript_data.get("speech_final", False)
                                    }
                                    await websocket.send_json(response)
                except Exception as e:
                    print(f"❌ Stream error: {e}")

            await asyncio.gather(
                process_stream(stream_manager.candidate_stream),
                process_stream(stream_manager.interviewer_stream),
                return_exceptions=True
            )

        audio_task = asyncio.create_task(handle_audio())
        transcript_task = asyncio.create_task(handle_transcripts())

        done, pending = await asyncio.wait(
            [audio_task, transcript_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()

    except Exception as e:
        print(f"❌ Deepgram error: {e}")
    finally:
        should_keepalive = False
        if keepalive_task:
            keepalive_task.cancel()
        await stream_manager.close_all()
        try:
            await websocket.close()
        except:
            pass
        print("🔌 Deepgram closed\n")