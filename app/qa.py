import asyncio
import json
import openai
from typing import Optional, Dict, Any

from app.config import DEFAULT_MODEL, OPENAI_API_KEY

RESPONSE_STYLES = {
    "concise": {
        "name": "Concise Professional",
        "prompt": """You are a concise interview assistant. Provide brief, professional answers in 2-3 sentences.
Focus on the core information without elaboration. Be direct and efficient."""
    },
    "detailed": {
        "name": "Detailed Professional",
        "prompt": """You are a detailed interview assistant. Provide comprehensive answers with:
- Clear explanation of the concept
- Relevant examples from experience
- Practical insights
Keep responses around 150 words, professional and well-structured."""
    },
    "storytelling": {
        "name": "Storytelling",
        "prompt": """You are an engaging interview assistant using storytelling techniques.
Structure answers using STAR format when appropriate:
- Situation: Set the context
- Task: Describe the challenge
- Action: Explain what you did
- Result: Share the outcome
Make responses compelling and memorable while remaining professional."""
    },
    "technical": {
        "name": "Technical Expert",
        "prompt": """You are a technical interview expert. Provide in-depth technical answers:
- Explain concepts clearly with proper terminology
- Include code examples when relevant
- Discuss trade-offs and best practices
Be thorough but avoid unnecessary jargon."""
    }
}

QUESTION_DETECTION_PROMPT = """You are an intelligent interview assistant that processes conversation transcripts in real-time.

Your task:
1. Analyze the incoming transcript text
2. Extract the EXACT question being asked (remove ONLY the preamble, but keep the question wording exactly as stated)
3. If a question is detected, return it in this EXACT format:
   QUESTION: [extracted question - keep original wording]
   ANSWER: [your answer]
4. If it's just casual conversation, greetings (like "hi", "hello"), or incomplete thoughts, respond with exactly: "SKIP"

Guidelines for extracting questions:
- Remove conversational preamble ONLY
- DO NOT rephrase the question - extract it EXACTLY as asked
- Keep the question wording completely unchanged
- Extract from the first question word to the question mark
- Preserve ALL technical terms, context, and original phrasing

Response format:
- If question detected: 
  QUESTION: [exact question with original wording]
  ANSWER: [your detailed answer]
- If no question: SKIP

CRITICAL: Do NOT rephrase or rewrite the question. Extract it EXACTLY as spoken.
"""

async def process_transcript_with_ai(
    transcript: str,
    settings: Dict[str, Any],
    persona_data: Optional[Dict] = None,
    custom_style_prompt: Optional[str] = None
) -> Dict[str, Any]:
    try:
        print(f"🤖 AI Processing transcript: {transcript[:100]}...")
        response_style_id = settings.get("selectedResponseStyleId", "concise")
        if custom_style_prompt:
            style_prompt = custom_style_prompt
        else:
            style_config = RESPONSE_STYLES.get(response_style_id, RESPONSE_STYLES["concise"])
            style_prompt = style_config["prompt"]
        system_prompt = QUESTION_DETECTION_PROMPT + "\n\n" + style_prompt
        if persona_data:
            system_prompt += f"""

CANDIDATE CONTEXT:
- Position: {persona_data.get('position', 'N/A')}
- Company: {persona_data.get('company_name', 'N/A')}
"""
            if persona_data.get('company_description'):
                system_prompt += f"- Company Description: {persona_data.get('company_description')}\n"
            if persona_data.get('job_description'):
                system_prompt += f"- Job Description: {persona_data.get('job_description')}\n"
            if persona_data.get('resume_text'):
                system_prompt += f"\nCANDIDATE RESUME:\n{persona_data.get('resume_text')}\n"
                system_prompt += "\nIMPORTANT: Use the resume information to provide accurate, personalized answers.\n"
        prog_lang = settings.get("programmingLanguage", "Python")
        system_prompt += f"\n\nWhen providing code examples, use {prog_lang}."
        if settings.get("interviewInstructions"):
            system_prompt += f"\n\nADDITIONAL INSTRUCTIONS:\n{settings['interviewInstructions']}"
        model = settings.get("defaultModel", DEFAULT_MODEL)
        print(f"🤖 Calling OpenAI with model: {model}")
        response = await asyncio.to_thread(
            lambda: openai.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Transcript: {transcript}"}
                ],
                temperature=0.5,
                max_tokens=400,
                timeout=20
            )
        )
        result_text = response.choices[0].message.content.strip()
        print(f"🤖 OpenAI response: {result_text[:200]}...")
        if result_text.upper() == "SKIP" or "SKIP" in result_text.upper():
            print("⏭ Skipping - not a question")
            return {"has_question": False, "question": None, "answer": None}
        question = None
        answer = None
        if "QUESTION:" in result_text and "ANSWER:" in result_text:
            parts = result_text.split("ANSWER:", 1)
            question = parts[0].replace("QUESTION:", "").strip()
            answer = parts[1].strip() if len(parts) > 1 else ""
            print(f"✅ Extracted Q: {question[:50]}... A: {answer[:50]}...")
        else:
            question = transcript
            answer = result_text
            print(f"✅ Using full response - Q: {question[:50]}... A: {answer[:50]}...")
        return {
            "has_question": True,
            "question": question,
            "answer": answer
        }
    except Exception as e:
        print(f"❌ AI error: {e}")
        import traceback
        traceback.print_exc()
        return {"has_question": False, "question": None, "answer": None}