# app/mock_interview.py
"""
Mock Interview Module with Analytics Support

Features:
- Context-aware question generation
- Intelligent question sequencing (Q1-2: ice breakers, Q3-5: behavioral, Q6-8: technical, Q9+: problem-solving)
- Answer evaluation with detailed scoring
- 🔥 ANALYTICS: Performance tracking, category scoring, trend analysis
- Voice generation for AI interviewer mode
"""

import random
import json
from typing import Dict, List, Optional
from app.ai_router import ask_ai
from app.client.openai_tts import text_to_speech_base64


# =========================================================
# FALLBACK QUESTIONS (IF AI GENERATION FAILS)
# =========================================================
FALLBACK_QUESTIONS = {
    "easy": [
        "Tell me about yourself and your background.",
        "What interests you about this role?",
        "What are your greatest strengths?",
        "Where do you see yourself in 5 years?",
        "Why do you want to work for our company?",
        "What motivates you in your work?",
        "Describe your ideal work environment.",
    ],
    "medium": [
        "Tell me about a challenging project you worked on.",
        "How do you handle tight deadlines and pressure?",
        "Describe a time when you had to learn a new technology quickly.",
        "How do you prioritize tasks when working on multiple projects?",
        "Tell me about a time you disagreed with a team member.",
        "What's your approach to debugging complex issues?",
        "How do you stay updated with new technologies?",
    ],
    "hard": [
        "Describe a time when you had to make a difficult technical decision with limited information.",
        "Tell me about a project that failed and what you learned from it.",
        "How would you scale a system to handle 10x more traffic?",
        "Explain a complex technical concept to someone non-technical.",
        "Describe the most challenging bug you've ever fixed.",
        "How do you balance technical debt with feature development?",
        "Tell me about a time you had to refactor a large codebase.",
    ],
    "behavioral": [
        "Tell me about a time you showed leadership.",
        "Describe a situation where you had to adapt to significant changes.",
        "How do you handle constructive criticism?",
        "Tell me about a time you went above and beyond.",
        "Describe a conflict you had with a colleague and how you resolved it.",
        "How do you handle failure or setbacks?",
        "Tell me about a time you had to persuade someone to see things your way.",
    ],
    "coding": [
        "How would you implement a rate limiter?",
        "Explain how you would design a URL shortener service.",
        "How would you implement an LRU cache?",
        "Describe your approach to implementing a real-time chat application.",
        "How would you optimize a slow database query?",
        "Explain how you would implement authentication in a web application.",
        "How would you design a notification system?",
    ],
}


def get_fallback_question(question_number: int = 1) -> tuple[str, str]:
    """
    Returns (question, category) based on question number
    
    Maps question numbers to appropriate categories:
    - Q1-2: easy (ice breakers)
    - Q3-5: behavioral
    - Q6-8: medium/technical
    - Q9+: hard/coding
    """
    
    if question_number <= 2:
        category = "communication"
        difficulty = "easy"
    elif question_number <= 5:
        category = "behavioral"
        difficulty = "behavioral"
    elif question_number <= 8:
        category = "technical"
        difficulty = "medium"
    else:
        category = "problem_solving"
        difficulty = "coding" if question_number % 2 == 0 else "hard"
    
    if difficulty not in FALLBACK_QUESTIONS:
        difficulty = "medium"
    
    questions = FALLBACK_QUESTIONS[difficulty]
    return random.choice(questions), category


# =========================================================
# 🔥 ANSWER EVALUATION WITH DETAILED ANALYTICS
# =========================================================
async def evaluate_answer_with_analytics(
    question: str,
    answer: str,
    question_number: int,
    persona_data: Dict,
    settings: Dict,
    response_time_seconds: int = 0,
) -> Dict:
    """
    Evaluate answer with comprehensive analytics
    
    Returns:
        {
            "question": str,
            "category": str,  # behavioral, technical, communication, problem_solving
            "score": int,  # 0-100
            "key_points_covered": int,
            "key_points_expected": int,
            "feedback": str,
            "response_time_seconds": int,
            
            # Optional detailed breakdown
            "score_breakdown": {
                "content_relevance": int,
                "structure": int,
                "depth": int,
                "delivery": int
            },
            
            # Speech analysis (if available)
            "speech_analysis": {
                "word_count": int,
                "filler_words": int,
                "speaking_rate": int,
                "confidence_score": float
            }
        }
    """
    
    model = settings.get("default_model", "gpt-4o-mini")
    
    # Determine category based on question number
    if question_number <= 2:
        expected_category = "communication"
    elif question_number <= 5:
        expected_category = "behavioral"
    elif question_number <= 8:
        expected_category = "technical"
    else:
        expected_category = "problem_solving"
    
    # Build context
    context = ""
    if persona_data.get("position"):
        context += f"Role: {persona_data['position']}\n"
    if persona_data.get("company_name"):
        context += f"Company: {persona_data['company_name']}\n"
    
    # 🔥 ENHANCED EVALUATION PROMPT WITH ANALYTICS
    prompt = f"""You are an expert technical interviewer evaluating a candidate's answer.

{context}

QUESTION (#{question_number}):
{question}

CANDIDATE'S ANSWER:
{answer}

Response Time: {response_time_seconds} seconds

Provide a comprehensive evaluation in the following JSON format:

{{
    "category": "<one of: behavioral, technical, communication, problem_solving>",
    "overall_score": <0-100>,
    "key_points_covered": <number>,
    "key_points_expected": <number>,
    
    "score_breakdown": {{
        "content_relevance": <0-100>,
        "structure": <0-100>,
        "depth": <0-100>,
        "delivery": <0-100>
    }},
    
    "feedback": "<3-4 sentence constructive feedback>",
    
    "strengths": ["<specific strength 1>", "<specific strength 2>"],
    "improvements": ["<specific improvement 1>", "<specific improvement 2>"]
}}

Scoring Guidelines:
- 90-100: Excellent, comprehensive answer with strong examples
- 75-89: Good answer, covers main points well
- 60-74: Acceptable, missing some depth or examples
- 40-59: Needs improvement, vague or incomplete
- 0-39: Poor, doesn't address the question

Be constructive and encouraging while being honest. Focus on actionable feedback."""

    try:
        messages = [
            {"role": "system", "content": "You are an expert interview evaluator. Always respond in valid JSON format only."},
            {"role": "user", "content": prompt}
        ]
        
        response = await ask_ai(model, messages)
        
        # Parse JSON response
        try:
            # Clean response (remove markdown code blocks if present)
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.startswith("```"):
                clean_response = clean_response[3:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()
            
            evaluation = json.loads(clean_response)
            
            # 🔥 CALCULATE SPEECH METRICS
            words = answer.split()
            word_count = len(words)
            
            # Simple filler word detection
            filler_words = ["um", "uh", "like", "you know", "basically", "actually", "literally"]
            filler_count = sum(1 for word in words if word.lower() in filler_words)
            
            # Speaking rate (words per minute)
            speaking_rate = int((word_count / response_time_seconds) * 60) if response_time_seconds > 0 else 140
            
            # Confidence score (heuristic based on score and fillers)
            overall_score = evaluation.get("overall_score", 0)
            confidence_score = round(min(10, (overall_score / 10) - (filler_count * 0.2)), 1)
            
            evaluation["speech_analysis"] = {
                "word_count": word_count,
                "filler_words": filler_count,
                "speaking_rate": speaking_rate,
                "confidence_score": max(1, confidence_score)
            }
            
            # Ensure all required fields exist
            evaluation["question"] = question
            evaluation["score"] = evaluation.get("overall_score", 0)
            evaluation["response_time_seconds"] = response_time_seconds
            
            # Use AI's category or fallback to expected
            if not evaluation.get("category"):
                evaluation["category"] = expected_category
            
            print(f"✅ Evaluation complete: {evaluation['score']}/100")
            return evaluation
            
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON parse error: {e}, raw response: {response[:200]}")
            
            # Fallback evaluation
            return {
                "question": question,
                "category": expected_category,
                "score": 70,
                "overall_score": 70,
                "key_points_covered": 3,
                "key_points_expected": 5,
                "score_breakdown": {
                    "content_relevance": 70,
                    "structure": 70,
                    "depth": 70,
                    "delivery": 70
                },
                "feedback": "Answer received. " + response[:300],
                "strengths": ["Provided a response"],
                "improvements": ["Could provide more specific details"],
                "response_time_seconds": response_time_seconds,
                "speech_analysis": {
                    "word_count": len(answer.split()),
                    "filler_words": 0,
                    "speaking_rate": 140,
                    "confidence_score": 7.0
                }
            }
    
    except Exception as e:
        print(f"❌ Answer evaluation failed: {e}")
        return {
            "question": question,
            "category": expected_category,
            "score": 0,
            "overall_score": 0,
            "key_points_covered": 0,
            "key_points_expected": 5,
            "score_breakdown": {
                "content_relevance": 0,
                "structure": 0,
                "depth": 0,
                "delivery": 0
            },
            "feedback": "Unable to evaluate answer at this time. Please try again.",
            "strengths": [],
            "improvements": ["System error - please retry"],
            "response_time_seconds": response_time_seconds,
            "speech_analysis": {
                "word_count": 0,
                "filler_words": 0,
                "speaking_rate": 0,
                "confidence_score": 0
            }
        }


# =========================================================
# AI QUESTION GENERATION (EXISTING - NO CHANGES)
# =========================================================
async def generate_question_with_voice(
    persona_data: Dict,
    settings: Dict,
    previous_questions: List[str],
    question_number: int = 1,
    voice: str = "alloy",
    include_audio: bool = True,
) -> Optional[Dict]:
    """
    Generate context-aware interview question with intelligent progression
    
    Question flow based on number:
    - Q1-2: Ice breakers (Tell me about yourself, Why this company)
    - Q3-5: Behavioral (STAR method, teamwork, challenges)
    - Q6-8: Technical/Domain specific (based on role)
    - Q9+: Problem-solving/Coding challenges
    """
    
    model = settings.get("default_model", "gpt-4o-mini")
    
    # Determine phase
    if question_number <= 2:
        phase = "icebreaker"
        category = "communication"
        phase_guidance = "Ask a warm-up question about background, interests, or basic skills. Keep it friendly and straightforward."
    elif question_number <= 5:
        phase = "behavioral"
        category = "behavioral"
        phase_guidance = "Ask a behavioral question using STAR format. Focus on soft skills, teamwork, problem-solving, or past experiences."
    elif question_number <= 8:
        phase = "technical"
        category = "technical"
        phase_guidance = "Ask a technical or domain-specific question relevant to the role. Focus on expertise, methodologies, tools."
    else:
        phase = "problem_solving"
        category = "problem_solving"
        phase_guidance = "Ask a challenging problem-solving question, case study, or coding problem."
    
    print(f"🎯 [Mock Q{question_number}] Phase: {phase}, Category: {category}")
    
    # Build context
    context_parts = []
    if persona_data.get("position"):
        context_parts.append(f"Position: {persona_data['position']}")
    if persona_data.get("company_name"):
        context_parts.append(f"Company: {persona_data['company_name']}")
    if persona_data.get("resume_text"):
        context_parts.append(f"Background:\n{persona_data['resume_text'][:2000]}")
    
    context = "\n".join(context_parts) if context_parts else "No specific context"
    
    # Previous questions
    prev_q_text = ""
    if previous_questions:
        prev_q_text = "\n\nPREVIOUSLY ASKED (DO NOT REPEAT):\n" + "\n".join(
            f"- {q}" for q in previous_questions[-10:]
        )
    
    # Generate question
    prompt = f"""You are an expert interviewer conducting question #{question_number}.

CANDIDATE CONTEXT:
{context}
{prev_q_text}

PHASE: {phase.upper()}
CATEGORY: {category}

TASK:
{phase_guidance}

RULES:
1. Make it relevant to the candidate's background
2. DO NOT repeat previous questions
3. Keep it clear, professional, 1-3 sentences max
4. Output ONLY the question itself - no preamble, no quotes
5. Just the question, nothing else

Generate ONE interview question now:"""

    try:
        messages = [
            {"role": "system", "content": "You are an expert interviewer. Output only the question itself, nothing else."},
            {"role": "user", "content": prompt}
        ]
        
        question_text = await ask_ai(model, messages)
        question_text = question_text.strip()
        
        # Clean unwanted prefixes
        unwanted_prefixes = [
            "here's a question:", "here is a question:", "question:",
            "here's one:", "here is one:", "interview question:",
        ]
        question_lower = question_text.lower()
        for prefix in unwanted_prefixes:
            if question_lower.startswith(prefix):
                question_text = question_text[len(prefix):].strip()
                break
        
        # Remove quotes
        if (question_text.startswith('"') and question_text.endswith('"')) or \
           (question_text.startswith("'") and question_text.endswith("'")):
            question_text = question_text[1:-1].strip()
        
        print(f"✅ Generated: {question_text[:80]}...")
        
        # Generate audio
        audio_base64 = None
        if include_audio:
            try:
                audio_base64 = text_to_speech_base64(text=question_text, voice=voice)
                print(f"🔊 Audio generated")
            except Exception as e:
                print(f"⚠️ TTS failed: {e}")
        
        return {
            "question": question_text,
            "category": category,  # 🔥 NEW: Include category
            "audio": audio_base64,
            "voice": voice,
            "question_number": question_number,
            "phase": phase,
        }
    
    except Exception as e:
        print(f"❌ AI question generation failed: {e}")
        return None


# Keep other existing functions unchanged...

# =========================================================
# BATCH INTERVIEW GENERATION
# =========================================================
async def generate_interview_set(
    persona_data: Dict,
    settings: Dict,
    question_count: int = 5,
    include_voice: bool = False,
) -> List[str]:
    """
    Generate a full set of interview questions
    """
    questions = []
    
    # We'll generate them sequentially to maintain flow
    for i in range(1, question_count + 1):
        result = await generate_question_with_voice(
            persona_data=persona_data,
            settings=settings,
            previous_questions=questions,
            question_number=i,
            include_audio=include_voice
        )
        
        if result:
            questions.append(result["question"])
        else:
            # Fallback if generation fails
            fallback, _ = get_fallback_question(i)
            questions.append(fallback)
            
    return questions


# =========================================================
# BACKWARD COMPATIBILITY
# =========================================================
async def evaluate_answer(
    question: str,
    answer: str,
    persona_data: Dict,
    settings: Dict,
) -> Dict:
    """
    Legacy wrapper for evaluate_answer_with_analytics
    """
    return await evaluate_answer_with_analytics(
        question=question,
        answer=answer,
        question_number=1,  # Default
        persona_data=persona_data,
        settings=settings,
        response_time_seconds=0
    )
