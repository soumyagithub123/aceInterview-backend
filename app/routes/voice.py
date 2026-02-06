# app/routes/voice.py
"""
Voice generation routes for mock interviews
Provides text-to-speech conversion for AI interviewer
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.client.openai_tts import text_to_speech_base64
from app.ws.session_manager import get_session
from app.mock_interview import (
    generate_question_with_voice,
    generate_interview_set,
    get_fallback_question,
    evaluate_answer,
)

router = APIRouter(prefix="/api/voice", tags=["voice"])


# ---------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------
class VoiceRequest(BaseModel):
    text: str
    voice: Optional[str] = "alloy"
    model: Optional[str] = "gpt-4o-mini-tts"


class MockQuestionRequest(BaseModel):
    session_id: str
    difficulty: Optional[str] = "medium"
    voice: Optional[str] = "alloy"
    include_audio: Optional[bool] = True


class MockInterviewSetRequest(BaseModel):
    session_id: str
    question_count: Optional[int] = 5
    include_voice: Optional[bool] = False


class EvaluateAnswerRequest(BaseModel):
    session_id: str
    question: str
    answer: str


# ---------------------------------------------------------
# Basic TTS Endpoint
# ---------------------------------------------------------
@router.post("")
async def generate_voice(payload: VoiceRequest):
    """
    Convert text to speech (base64 audio)
    
    Used for:
    - Mock interview AI voice
    - Custom voice generation
    - TTS testing
    """
    
    if not payload.text or not payload.text.strip():
        raise HTTPException(
            status_code=400,
            detail="Text is required for voice generation"
        )
    
    try:
        audio_base64 = text_to_speech_base64(
            text=payload.text,
            voice=payload.voice or "alloy",
            model=payload.model or "gpt-4o-mini-tts",
        )
        
        if not audio_base64:
            raise RuntimeError("Empty audio response from TTS")
        
        return {
            "audio": audio_base64,
            "voice": payload.voice or "alloy",
            "model": payload.model or "gpt-4o-mini-tts",
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Voice generation failed: {str(e)}"
        )


# ---------------------------------------------------------
# Mock Interview: Single Question
# ---------------------------------------------------------
@router.post("/mock-question")
async def generate_mock_question(payload: MockQuestionRequest):
    """
    Generate AI interview question with optional voice
    
    Features:
    - Context-aware based on resume/persona
    - Multiple difficulty levels
    - Automatic voice generation
    - Avoids duplicate questions
    
    Returns:
        {
            "type": "mock_question",
            "question": str,
            "audio": base64 (optional),
            "voice": str,
            "difficulty": str
        }
    """
    
    session = get_session(payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    settings = session.get("settings", {})
    persona_data = session.get("persona_data", {})
    prev_questions = list(session.get("prev_questions", []))
    
    try:
        result = await generate_question_with_voice(
            persona_data=persona_data,
            settings=settings,
            previous_questions=prev_questions,
            difficulty=payload.difficulty or "medium",
            voice=payload.voice or "alloy",
            include_audio=payload.include_audio,
        )
        
        if not result:
            # Fallback to preset question
            fallback_q = get_fallback_question(payload.difficulty or "medium")
            
            audio = None
            if payload.include_audio:
                try:
                    audio = text_to_speech_base64(
                        text=fallback_q,
                        voice=payload.voice or "alloy",
                    )
                except Exception:
                    pass
            
            result = {
                "question": fallback_q,
                "audio": audio,
                "voice": payload.voice or "alloy",
                "difficulty": payload.difficulty or "medium",
                "is_fallback": True,
            }
        
        # Store question in session
        if "prev_questions" not in session:
            session["prev_questions"] = []
        session["prev_questions"].append(result["question"])
        
        return {
            "type": "mock_question",
            "question": result["question"],
            "audio": result.get("audio"),
            "voice": result["voice"],
            "difficulty": result["difficulty"],
            "is_fallback": result.get("is_fallback", False),
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Mock question generation failed: {str(e)}"
        )


# ---------------------------------------------------------
# Mock Interview: Generate Full Set
# ---------------------------------------------------------
@router.post("/mock-interview-set")
async def generate_mock_interview_set(payload: MockInterviewSetRequest):
    """
    Generate a complete set of interview questions
    
    Useful for:
    - Preparing questions in advance
    - Creating structured interview flow
    - Batch generation for efficiency
    
    Returns:
        {
            "type": "interview_set",
            "questions": [...],
            "total_count": int
        }
    """
    
    session = get_session(payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    settings = session.get("settings", {})
    persona_data = session.get("persona_data", {})
    
    try:
        questions = await generate_interview_set(
            persona_data=persona_data,
            settings=settings,
            question_count=payload.question_count or 5,
            include_voice=payload.include_voice or False,
        )
        
        return {
            "type": "interview_set",
            "questions": questions,
            "total_count": len(questions),
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Interview set generation failed: {str(e)}"
        )


# ---------------------------------------------------------
# Mock Interview: Evaluate Answer
# ---------------------------------------------------------
@router.post("/evaluate-answer")
async def evaluate_mock_answer(payload: EvaluateAnswerRequest):
    """
    Evaluate candidate's answer to a mock interview question
    
    Returns:
        {
            "type": "answer_evaluation",
            "score": int (1-10),
            "feedback": str,
            "strengths": List[str],
            "improvements": List[str]
        }
    """
    
    session = get_session(payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    settings = session.get("settings", {})
    persona_data = session.get("persona_data", {})
    
    try:
        evaluation = await evaluate_answer(
            question=payload.question,
            answer=payload.answer,
            persona_data=persona_data,
            settings=settings,
        )
        
        return {
            "type": "answer_evaluation",
            **evaluation
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Answer evaluation failed: {str(e)}"
        )