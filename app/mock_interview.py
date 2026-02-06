# app/mock_interview.py
"""
Mock Interview Question Generation Module

Generates context-aware interview questions based on:
- User's resume/persona
- Difficulty level
- Previous questions (to avoid repetition)
- Company/role context

Supports voice generation for AI interviewer mode
"""

import random
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


def get_fallback_question(question_number: int = 1) -> str:
    """
    Returns a fallback question based on question number/phase.
    Used when AI generation fails.
    
    Maps question numbers to appropriate difficulty:
    - Q1-2: easy (ice breakers)
    - Q3-5: behavioral
    - Q6-8: medium/technical
    - Q9+: hard/coding
    """
    
    if question_number <= 2:
        difficulty = "easy"
    elif question_number <= 5:
        difficulty = "behavioral"
    elif question_number <= 8:
        difficulty = "medium"
    else:
        # Alternate between hard and coding for advanced questions
        difficulty = "coding" if question_number % 2 == 0 else "hard"
    
    if difficulty not in FALLBACK_QUESTIONS:
        difficulty = "medium"
    
    questions = FALLBACK_QUESTIONS[difficulty]
    return random.choice(questions)


# =========================================================
# AI QUESTION GENERATION WITH INTELLIGENT SEQUENCING
# =========================================================
async def generate_question_with_voice(
    persona_data: Dict,
    settings: Dict,
    previous_questions: List[str],
    question_number: int = 1,  # ✅ CHANGED from difficulty
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
    
    Args:
        persona_data: User's resume/profile data
        settings: User settings (model, etc.)
        previous_questions: List of already asked questions
        question_number: Current question number (determines type/difficulty)
        voice: Voice to use for TTS
        include_audio: Whether to generate audio
    
    Returns:
        {
            "question": str,
            "audio": base64 (if include_audio=True),
            "voice": str,
            "question_number": int,
            "phase": str  # "icebreaker", "behavioral", "technical", "problem_solving"
        }
    """
    
    model = settings.get("default_model", "gpt-4o-mini")
    
    # =========================================================
    # PHASE DETECTION BASED ON QUESTION NUMBER
    # =========================================================
    if question_number <= 2:
        phase = "icebreaker"
        phase_guidance = "Ask a warm-up question about background, interests, or basic skills. Keep it friendly and straightforward. Examples: 'Tell me about yourself', 'Why are you interested in this role?'"
    elif question_number <= 5:
        phase = "behavioral"
        phase_guidance = "Ask a behavioral question using STAR format (Situation, Task, Action, Result). Focus on soft skills, teamwork, problem-solving, or past experiences. Start with 'Tell me about a time when...' or 'Describe a situation where...'"
    elif question_number <= 8:
        phase = "technical"
        phase_guidance = "Ask a technical or domain-specific question relevant to the role. Focus on expertise, methodologies, tools, or real-world application of skills."
    else:
        phase = "problem_solving"
        phase_guidance = "Ask a challenging problem-solving question, case study, or coding problem. Make it analytical and relevant to the role."
    
    print(f"🎯 [Mock Q{question_number}] Phase: {phase}")
    
    # =========================================================
    # BUILD CONTEXT FROM PERSONA
    # =========================================================
    context_parts = []
    
    if persona_data.get("position"):
        context_parts.append(f"Position applying for: {persona_data['position']}")
    
    if persona_data.get("company_name"):
        context_parts.append(f"Company: {persona_data['company_name']}")
    
    if persona_data.get("company_description"):
        context_parts.append(f"Company description: {persona_data['company_description'][:500]}")
    
    if persona_data.get("job_description"):
        context_parts.append(f"Job description: {persona_data['job_description'][:500]}")
    
    if persona_data.get("resume_text"):
        context_parts.append(f"Candidate's background:\n{persona_data['resume_text'][:2000]}")
    
    context = "\n".join(context_parts) if context_parts else "No specific context available"
    
    # =========================================================
    # BUILD PREVIOUS QUESTIONS CONTEXT
    # =========================================================
    prev_q_text = ""
    if previous_questions:
        prev_q_text = "\n\nPREVIOUSLY ASKED QUESTIONS (DO NOT REPEAT):\n" + "\n".join(
            f"- {q}" for q in previous_questions[-10:]  # Last 10 questions
        )
    
    # =========================================================
    # GENERATE QUESTION USING AI
    # =========================================================
    prompt = f"""You are an expert technical interviewer conducting question #{question_number} of a job interview.

CANDIDATE CONTEXT:
{context}
{prev_q_text}

INTERVIEW PHASE: {phase.upper()}
Question Number: {question_number}

TASK:
Generate ONE interview question following these requirements:

PHASE GUIDANCE:
{phase_guidance}

RULES:
1. Make the question relevant to the candidate's background and the role
2. DO NOT repeat any previously asked questions
3. Keep the question clear, professional, and focused
4. The question should be 1-3 sentences maximum
5. Output ONLY the question text itself - no preamble, no explanations
6. Do NOT include phrases like "Here's a question" or quotation marks
7. Just the question, nothing else

Generate the question now:"""

    try:
        messages = [
            {
                "role": "system",
                "content": "You are an expert interviewer. Output ONLY the question text, nothing else."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        question_text = await ask_ai(model, messages)
        
        if not question_text or len(question_text.strip()) < 10:
            print(f"⚠️ AI returned invalid question: {question_text}")
            return None
        
        # Clean up the question
        question_text = question_text.strip()
        
        # Remove common unwanted prefixes
        unwanted_prefixes = [
            "here's a question:",
            "i would ask:",
            "question:",
            "here is a question:",
            "let me ask:",
        ]
        
        question_lower = question_text.lower()
        for prefix in unwanted_prefixes:
            if question_lower.startswith(prefix):
                question_text = question_text[len(prefix):].strip()
                break
        
        # Remove surrounding quotes if present
        if (question_text.startswith('"') and question_text.endswith('"')) or \
           (question_text.startswith("'") and question_text.endswith("'")):
            question_text = question_text[1:-1].strip()
        
        print(f"✅ Generated: {question_text[:80]}...")
        
        # =========================================================
        # GENERATE AUDIO IF REQUESTED
        # =========================================================
        audio_base64 = None
        if include_audio:
            try:
                audio_base64 = text_to_speech_base64(
                    text=question_text,
                    voice=voice,
                )
                print(f"🔊 Audio generated successfully")
            except Exception as e:
                print(f"⚠️ TTS generation failed: {e}")
                # Continue without audio
        
        return {
            "question": question_text,
            "audio": audio_base64,
            "voice": voice,
            "question_number": question_number,
            "phase": phase,
        }
    
    except Exception as e:
        print(f"❌ AI question generation failed: {e}")
        return None


# =========================================================
# BATCH QUESTION GENERATION
# =========================================================
async def generate_interview_set(
    persona_data: Dict,
    settings: Dict,
    question_count: int = 5,
    include_voice: bool = False,
) -> List[Dict]:
    """
    Generate a set of interview questions in advance
    
    Useful for preparing a structured interview flow
    Mixes different difficulty levels for variety
    
    Args:
        persona_data: User's resume/profile
        settings: User settings
        question_count: Number of questions to generate
        include_voice: Whether to generate audio for each question
    
    Returns:
        List of question objects
    """
    
    # Mix of difficulties for a balanced interview
    difficulty_mix = []
    
    if question_count <= 3:
        difficulty_mix = ["easy", "medium", "medium"][:question_count]
    elif question_count <= 5:
        difficulty_mix = ["easy", "medium", "medium", "behavioral", "hard"][:question_count]
    else:
        # For longer interviews, create a balanced mix
        base_mix = ["easy", "medium", "medium", "behavioral", "hard", "coding"]
        while len(difficulty_mix) < question_count:
            difficulty_mix.extend(base_mix)
        difficulty_mix = difficulty_mix[:question_count]
    
    questions = []
    previous_questions = []
    
    for i, difficulty in enumerate(difficulty_mix):
        print(f"📝 Generating question {i+1}/{question_count} (difficulty: {difficulty})")
        
        result = await generate_question_with_voice(
            persona_data=persona_data,
            settings=settings,
            previous_questions=previous_questions,
            difficulty=difficulty,
            voice=settings.get("candidate_voice_settings", {}).get("voice", "alloy"),
            include_audio=include_voice,
        )
        
        if result:
            questions.append(result)
            previous_questions.append(result["question"])
        else:
            # Use fallback
            fallback_q = get_fallback_question(difficulty)
            
            audio = None
            if include_voice:
                try:
                    audio = text_to_speech_base64(
                        text=fallback_q,
                        voice=settings.get("candidate_voice_settings", {}).get("voice", "alloy"),
                    )
                except Exception:
                    pass
            
            questions.append({
                "question": fallback_q,
                "audio": audio,
                "voice": settings.get("candidate_voice_settings", {}).get("voice", "alloy"),
                "difficulty": difficulty,
                "is_fallback": True,
            })
            previous_questions.append(fallback_q)
    
    print(f"✅ Generated {len(questions)} questions")
    return questions


# =========================================================
# ANSWER EVALUATION (OPTIONAL)
# =========================================================
async def evaluate_answer(
    question: str,
    answer: str,
    persona_data: Dict,
    settings: Dict,
) -> Dict:
    """
    Evaluate a candidate's answer and provide feedback
    
    Args:
        question: The interview question
        answer: Candidate's answer
        persona_data: User profile
        settings: User settings
    
    Returns:
        {
            "score": int (1-10),
            "feedback": str,
            "strengths": List[str],
            "improvements": List[str]
        }
    """
    
    model = settings.get("default_model", "gpt-4o-mini")
    
    context = ""
    if persona_data.get("position"):
        context += f"Role: {persona_data['position']}\n"
    if persona_data.get("company_name"):
        context += f"Company: {persona_data['company_name']}\n"
    
    prompt = f"""You are an expert technical interviewer evaluating a candidate's answer.

{context}

QUESTION:
{question}

CANDIDATE'S ANSWER:
{answer}

Evaluate this answer and provide:
1. A score from 1-10
2. Brief feedback (3-4 sentences)
3. What was good about the answer
4. What could be improved

Format your response as JSON:
{{
    "score": <1-10>,
    "feedback": "<brief overall feedback>",
    "strengths": ["<strength 1>", "<strength 2>"],
    "improvements": ["<improvement 1>", "<improvement 2>"]
}}

Be constructive and encouraging while being honest."""

    try:
        messages = [
            {"role": "system", "content": "You are an expert interview evaluator. Always respond in valid JSON format."},
            {"role": "user", "content": prompt}
        ]
        
        response = await ask_ai(model, messages)
        
        # Try to parse as JSON
        import json
        try:
            evaluation = json.loads(response)
            return evaluation
        except json.JSONDecodeError:
            # Fallback if not proper JSON
            return {
                "score": 7,
                "feedback": response,
                "strengths": [],
                "improvements": []
            }
    
    except Exception as e:
        print(f"❌ Answer evaluation failed: {e}")
        return {
            "score": 0,
            "feedback": "Unable to evaluate answer at this time.",
            "strengths": [],
            "improvements": []
        }