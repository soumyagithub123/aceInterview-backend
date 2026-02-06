# app/ws/ws_live_interview.py
"""
WebSocket Live Interview Handler with Mock Interview Analytics

Features:
- Real-time transcript processing
- Mock interview mode with AI questions
- 🔥 COMPREHENSIVE ANALYTICS: Performance tracking, scoring, feedback
- Session management
- Keepalive for production environments
"""

import asyncio
import json
import time
import traceback
from typing import Optional, Dict, List

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


# =========================================================
# 🔥 SESSION ANALYTICS TRACKER
# =========================================================
class MockInterviewAnalytics:
    """Track performance metrics throughout mock interview"""
    
    def __init__(self):
        self.questions_data: List[Dict] = []
        self.start_time = time.time()
        self.end_time = None
    
    def add_question_evaluation(self, evaluation: Dict):
        """Add evaluated question to analytics"""
        self.questions_data.append(evaluation)
        print(f"📊 Analytics: {len(self.questions_data)} questions tracked")
    
    def calculate_final_analytics(self) -> Dict:
        """Calculate comprehensive analytics when interview ends"""
        
        if not self.questions_data:
            return self._empty_analytics()
        
        self.end_time = time.time()
        duration_minutes = int((self.end_time - self.start_time) / 60)
        
        # Overall score
        total_score = sum(q.get("score", 0) for q in self.questions_data)
        avg_score = int(total_score / len(self.questions_data))
        
        # Category analysis
        categories = {}
        for q in self.questions_data:
            cat = q.get("category", "general")
            if cat not in categories:
                categories[cat] = {"scores": [], "count": 0}
            categories[cat]["scores"].append(q.get("score", 0))
            categories[cat]["count"] += 1
        
        category_analysis = {}
        for cat, data in categories.items():
            scores = data["scores"]
            avg = int(sum(scores) / len(scores))
            
            # Trend detection
            trend = "neutral"
            if len(scores) >= 2:
                first_half = scores[:len(scores)//2]
                second_half = scores[len(scores)//2:]
                first_avg = sum(first_half) / len(first_half)
                second_avg = sum(second_half) / len(second_half)
                
                if second_avg > first_avg + 5:
                    trend = "up"
                elif second_avg < first_avg - 5:
                    trend = "down"
            
            category_analysis[cat] = {
                "score": avg,
                "trend": trend,
                "feedback": self._get_category_feedback(cat, avg, trend)
            }
        
        # Time analysis
        response_times = [q.get("response_time_seconds", 0) for q in self.questions_data]
        response_times = [t for t in response_times if t > 0]
        
        avg_response_time = int(sum(response_times) / len(response_times)) if response_times else 0
        
        # Speech metrics
        total_words = sum(q.get("speech_analysis", {}).get("word_count", 0) for q in self.questions_data)
        total_duration = sum(q.get("response_time_seconds", 0) for q in self.questions_data)
        total_fillers = sum(q.get("speech_analysis", {}).get("filler_words", 0) for q in self.questions_data)
        
        avg_wpm = int((total_words / total_duration) * 60) if total_duration > 0 else 140
        avg_clarity = sum(q.get("speech_analysis", {}).get("confidence_score", 7) for q in self.questions_data) / len(self.questions_data)
        
        # Extract strengths and improvements
        strengths = self._extract_strengths(self.questions_data)
        improvements = self._extract_improvements(self.questions_data)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(category_analysis, avg_score)
        
        return {
            "overall_score": avg_score,
            "total_questions": len(self.questions_data),
            "completion_rate": 100,
            "duration_minutes": duration_minutes,
            
            "categories": category_analysis,
            
            "strengths": strengths,
            "improvements": improvements,
            
            "question_breakdown": [
                {
                    "number": i + 1,
                    "question": q.get("question", ""),
                    "category": q.get("category", "general"),
                    "score": q.get("score", 0),
                    "duration_seconds": q.get("response_time_seconds", 0),
                    "key_points_covered": q.get("key_points_covered", 0),
                    "key_points_expected": q.get("key_points_expected", 0),
                    "feedback": q.get("feedback", "")
                }
                for i, q in enumerate(self.questions_data)
            ],
            
            "time_analysis": {
                "avg_response_time": avg_response_time,
                "fastest_response": min(response_times) if response_times else 0,
                "slowest_response": max(response_times) if response_times else 0,
                "optimal_range": [90, 180]
            },
            
            "speech_metrics": {
                "avg_words_per_minute": avg_wpm,
                "filler_words_count": total_fillers,
                "pause_frequency": self._calculate_pause_frequency(avg_wpm),
                "clarity_score": round(avg_clarity, 1)
            },
            
            "recommendations": recommendations
        }
    
    def _empty_analytics(self) -> Dict:
        """Return empty analytics structure"""
        return {
            "overall_score": 0,
            "total_questions": 0,
            "completion_rate": 0,
            "duration_minutes": 0,
            "categories": {},
            "strengths": [],
            "improvements": [],
            "question_breakdown": [],
            "time_analysis": {
                "avg_response_time": 0,
                "fastest_response": 0,
                "slowest_response": 0,
                "optimal_range": [90, 180]
            },
            "speech_metrics": {
                "avg_words_per_minute": 0,
                "filler_words_count": 0,
                "pause_frequency": "moderate",
                "clarity_score": 0
            },
            "recommendations": []
        }
    
    def _get_category_feedback(self, category: str, score: int, trend: str) -> str:
        """Generate feedback for category"""
        feedback_map = {
            "communication": {
                "high": "Excellent communication skills demonstrated",
                "medium": "Good communication, room for improvement",
                "low": "Work on clarity and articulation"
            },
            "technical": {
                "high": "Strong technical knowledge",
                "medium": "Solid fundamentals, deepen expertise",
                "low": "Focus on core technical concepts"
            },
            "behavioral": {
                "high": "Great use of STAR method and examples",
                "medium": "Good examples, could be more specific",
                "low": "Provide more concrete examples"
            },
            "problem_solving": {
                "high": "Excellent analytical approach",
                "medium": "Good problem-solving structure",
                "low": "Work on systematic problem breakdown"
            }
        }
        
        level = "high" if score >= 80 else "medium" if score >= 60 else "low"
        base = feedback_map.get(category, {}).get(level, "Continue practicing")
        
        if trend == "up":
            return f"{base} - Showing improvement!"
        elif trend == "down":
            return f"{base} - Focus area for next session"
        return base
    
    def _extract_strengths(self, questions: List[Dict]) -> List[str]:
        """Extract top strengths from high-scoring questions"""
        strengths = []
        
        high_score_qs = [q for q in questions if q.get("score", 0) >= 80]
        
        if len(high_score_qs) >= len(questions) * 0.6:
            strengths.append("Consistently high performance across multiple questions")
        
        # Category-specific strengths
        categories_excelled = {}
        for q in high_score_qs:
            cat = q.get("category")
            if cat:
                categories_excelled[cat] = categories_excelled.get(cat, 0) + 1
        
        for cat, count in categories_excelled.items():
            if count >= 2:
                strengths.append(f"Strong {cat.replace('_', ' ')} skills demonstrated")
        
        # Speech quality
        avg_fillers = sum(q.get("speech_analysis", {}).get("filler_words", 0) for q in questions) / len(questions)
        if avg_fillers < 2:
            strengths.append("Minimal filler words - clear communication")
        
        return strengths[:4]
    
    def _extract_improvements(self, questions: List[Dict]) -> List[str]:
        """Extract improvement areas from lower-scoring questions"""
        improvements = []
        
        low_score_qs = [q for q in questions if q.get("score", 0) < 70]
        
        for q in low_score_qs:
            if q.get("key_points_covered", 0) < q.get("key_points_expected", 0):
                cat = q.get("category", "general")
                improvements.append(f"Cover all key points when discussing {cat} topics")
        
        # Time management
        response_times = [q.get("response_time_seconds", 0) for q in questions]
        if any(t > 210 for t in response_times):
            improvements.append("Work on being more concise - aim for 2-3 minute responses")
        if any(t < 60 for t in response_times):
            improvements.append("Provide more detailed responses with specific examples")
        
        return list(set(improvements))[:4]
    
    def _generate_recommendations(self, category_analysis: Dict, overall_score: int) -> List[Dict]:
        """Generate personalized recommendations"""
        recommendations = []
        
        # Weak categories
        weak_cats = {cat: data for cat, data in category_analysis.items() if data["score"] < 70}
        
        for cat, data in weak_cats.items():
            recommendations.append({
                "title": f"Improve {cat.replace('_', ' ').title()} Skills",
                "description": f"Your {cat} responses averaged {data['score']}/100. Focus on this area.",
                "priority": "high" if data["score"] < 60 else "medium",
                "resources": [
                    f"{cat.title()} Interview Guide",
                    "Practice Questions",
                    "Sample Responses"
                ]
            })
        
        # General recommendation if overall score needs improvement
        if overall_score < 80:
            recommendations.append({
                "title": "Practice Mock Interviews",
                "description": "Regular practice will improve confidence and performance",
                "priority": "high",
                "resources": [
                    "Interview Practice Platform",
                    "Peer Mock Sessions",
                    "Video Self-Review"
                ]
            })
        
        return recommendations[:3]
    
    def _calculate_pause_frequency(self, wpm: int) -> str:
        """Calculate pause frequency based on speaking rate"""
        if wpm < 120:
            return "high"
        elif wpm > 160:
            return "low"
        else:
            return "moderate"


# =========================================================
# SESSION INIT ENDPOINT
# =========================================================
@router.post("/session/init")
async def init_session(request: SessionInitRequest):
    """Session initialization endpoint"""
    result = await create_session(request)
    
    # 🔥 Add analytics tracker to session
    session = get_session(result["session_id"])
    if session:
        session["analytics"] = MockInterviewAnalytics()
        print(f"📊 Analytics tracker initialized for session {result['session_id']}")
    
    return result


# =========================================================
# WEBSOCKET ENDPOINT
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

            # =========================================================
            # SESSION END - 🔥 SEND ANALYTICS
            # =========================================================
            if msg_type == "session_end":
                sid = data.get("session_id")
                if sid:
                    session = get_session(sid)
                    
                    # 🔥 Calculate and send final analytics
                    if session and "analytics" in session:
                        analytics = session["analytics"].calculate_final_analytics()
                        
                        await safe_send({
                            "type": "session_analytics",
                            "analytics": analytics,
                            "timestamp": time.time()
                        })
                        
                        log(f"📊 Final analytics sent: {analytics['overall_score']}/100", "SUCCESS")
                    
                    delete_session(sid)
                continue

            # SESSION INIT
            if msg_type == "init":
                current_session_id = data.get("session_id")
                session = get_session(current_session_id)

                if not session:
                    await safe_send({"type": "error", "message": "Session not found"})
                    continue

                # Initialize analytics tracker if missing
                if "analytics" not in session:
                    session["analytics"] = MockInterviewAnalytics()

                transcript_accumulator = session["transcript_accumulator"]

                await safe_send({"type": "connected", "message": "Session ready"})
                continue

            # =========================================================
            # 🎤 MOCK INTERVIEW: REQUEST QUESTION
            # =========================================================
            if msg_type == "request_mock_question":
                if not current_session_id:
                    await safe_send({"type": "error", "message": "Session not initialized"})
                    continue
                
                question_number = data.get("question_number", 1)
                voice = data.get("voice", "alloy")
                include_audio = data.get("include_audio", True)
                
                log(f"🎤 Mock Q{question_number} requested")
                
                try:
                    session = get_session(current_session_id)
                    
                    # Generate AI question
                    from app.mock_interview import generate_question_with_voice, get_fallback_question
                    
                    result = await generate_question_with_voice(
                        persona_data=session["persona_data"],
                        settings=session["settings"],
                        previous_questions=list(session["prev_questions"]),
                        question_number=question_number,
                        voice=voice,
                        include_audio=include_audio,
                    )
                    
                    if result:
                        session["prev_questions"].append(result["question"])
                        
                        await safe_send({
                            "type": "mock_question",
                            "question": result["question"],
                            "category": result.get("category", "general"),  # 🔥 NEW
                            "audio": result.get("audio"),
                            "voice": voice,
                            "question_number": question_number,
                            "phase": result.get("phase", "general"),
                            "timestamp": time.time()
                        })
                        
                        log(f"✅ Mock Q{question_number} sent", "SUCCESS")
                    else:
                        # Fallback
                        fallback_q, category = get_fallback_question(question_number)
                        
                        from app.client.openai_tts import text_to_speech_base64
                        audio = None
                        if include_audio:
                            try:
                                audio = text_to_speech_base64(text=fallback_q, voice=voice)
                            except Exception:
                                pass
                        
                        session["prev_questions"].append(fallback_q)
                        
                        await safe_send({
                            "type": "mock_question",
                            "question": fallback_q,
                            "category": category,  # 🔥 NEW
                            "audio": audio,
                            "voice": voice,
                            "question_number": question_number,
                            "is_fallback": True,
                            "timestamp": time.time()
                        })
                
                except Exception as e:
                    log(f"❌ Mock question error: {e}", "ERROR")
                    await safe_send({
                        "type": "error",
                        "message": f"Failed to generate question: {str(e)}"
                    })
                
                continue

            # =========================================================
            # 🎤 MOCK INTERVIEW: EVALUATE ANSWER - 🔥 WITH ANALYTICS
            # =========================================================
            if msg_type == "evaluate_answer":
                if not current_session_id:
                    await safe_send({"type": "error", "message": "Session not initialized"})
                    continue
                
                question = data.get("question", "")
                answer = data.get("answer", "")
                question_number = data.get("question_number", 1)  # 🔥 NEW
                response_time = data.get("response_time_seconds", 0)  # 🔥 NEW
                get_feedback = data.get("get_feedback", True)
                
                if not question or not answer:
                    await safe_send({"type": "error", "message": "Question and answer required"})
                    continue
                
                log(f"📊 Evaluating Q{question_number}...")
                
                try:
                    session = get_session(current_session_id)
                    
                    await safe_send({"type": "feedback_generating"})
                    
                    # 🔥 COMPREHENSIVE EVALUATION WITH ANALYTICS
                    from app.mock_interview import evaluate_answer_with_analytics
                    
                    evaluation = await evaluate_answer_with_analytics(
                        question=question,
                        answer=answer,
                        question_number=question_number,
                        persona_data=session["persona_data"],
                        settings=session["settings"],
                        response_time_seconds=response_time,
                    )
                    
                    # 🔥 ADD TO ANALYTICS TRACKER
                    if "analytics" in session:
                        session["analytics"].add_question_evaluation(evaluation)
                    
                    # Send feedback to frontend
                    await safe_send({
                        "type": "answer_feedback",
                        "question": question,
                        "answer": answer,
                        "category": evaluation.get("category", "general"),
                        "score": evaluation.get("score", 0),
                        "feedback": evaluation.get("feedback", ""),
                        "key_points_covered": evaluation.get("key_points_covered", 0),
                        "key_points_expected": evaluation.get("key_points_expected", 0),
                        "timestamp": time.time()
                    })
                    
                    log(f"✅ Feedback sent: {evaluation['score']}/100", "SUCCESS")
                
                except Exception as e:
                    log(f"❌ Feedback error: {e}", "ERROR")
                    traceback.print_exc()
                    await safe_send({
                        "type": "error",
                        "message": f"Failed to generate feedback: {str(e)}"
                    })
                
                continue

            # =========================================================
            # TRANSCRIPT (EXISTING - NO CHANGES)
            # =========================================================
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