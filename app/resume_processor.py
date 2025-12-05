import asyncio
import os
import io
import pdfplumber
import requests
from openai import OpenAI
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)


async def extract_pdf_text(url: str) -> str:
    """Download and extract text from a PDF."""
    try:
        response = requests.get(url, timeout=20)
        if response.status_code != 200:
            return ""

        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            text = ""
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"

        return text.strip()
    except:
        return ""


async def summarize_resume(text: str) -> str:
    """Summarize resume text in FIRST PERSON as the candidate."""
    if not text or len(text) < 50:
        return ""

    prompt = f"""
You are converting this resume into a first-person narrative summary AS IF YOU ARE THE CANDIDATE.

CRITICAL RULES:
1. Write EVERYTHING in first person ("I", "my", "I have")
2. Start with: "My name is [NAME]" or "I am [NAME]"
3. Present all information as if YOU are the person in the resume
4. Keep it natural and conversational
5. Include: name, technical skills, experience level, key achievements, education

Example output style:
"My name is Alex Chen and I am currently pursuing a Bachelor of Technology in Computer Science and Engineering at XYZ University, with an expected graduation in July 2026. I have hands-on experience in web development and backend systems, and I'm proficient in Python, JavaScript, C, and C++. I've worked with frameworks like React, Node.js, and Firebase. One of my notable achievements includes developing an AI-powered content generation platform that improved efficiency by 70%, and I also designed a responsive e-commerce website that reduced bounce rates by 40%. I've completed certifications in Python programming and cloud computing from leading institutions."

Now convert this resume into a first-person summary:

{text[:12000]}
"""

    try:
        result = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.7
        )
        return result.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ OpenAI error: {e}")
        return ""


async def update_persona(persona_id: str, summary: str):
    """Save summary into the DB."""
    try:
        supabase.table("personas").update({
            "resume_text": summary
        }).eq("id", persona_id).execute()
        print(f"✅ Updated persona {persona_id} with first-person summary")
    except Exception as e:
        print(f"❌ DB update error: {e}")


async def process_unprocessed_resumes():
    """Core loop — checks every 30 seconds and processes missing ones."""
    print("🚀 Resume processor started (first-person mode)")
    
    while True:
        try:
            # Fetch personas missing resume_text
            result = supabase.table("personas").select(
                "id, resume_url, resume_text"
            ).execute()

            personas = [
                p for p in result.data
                if p.get("resume_url") and not p.get("resume_text")
            ]

            if personas:
                print(f"📄 Found {len(personas)} unprocessed resumes")

            for p in personas:
                persona_id = p["id"]
                url = p["resume_url"]
                
                print(f"📥 Processing resume for persona {persona_id}")
                
                # Extract text from PDF
                text = await extract_pdf_text(url)

                if not text:
                    print(f"⚠️ Could not extract text from {url}")
                    continue

                print(f"📝 Extracted {len(text)} characters, generating first-person summary...")

                # Generate first-person summary
                summary = await summarize_resume(text)
                
                if not summary:
                    print(f"⚠️ Could not generate summary")
                    continue

                # Save to database
                await update_persona(persona_id, summary)
                print(f"✔️ Successfully processed persona {persona_id}")

        except Exception as e:
            print(f"❌ Resume processor error: {e}")

        # Sleep before next check
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(process_unprocessed_resumes())