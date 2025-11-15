import os
import requests
import io
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI
import pdfplumber

# ---------------- CONFIG ----------------
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY or not OPENAI_API_KEY:
    raise ValueError("Missing required environment variables. Check your .env file!")

# Initialize clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# ---------------- FUNCTIONS ----------------

def fetch_pdf_text(url: str) -> str:
    """Download PDF from URL and extract text using pdfplumber."""
    try:
        print(f"📄 Downloading PDF from: {url}")
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            print(f"❌ Failed to fetch PDF: HTTP {response.status_code}")
            return ""

        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            text = ""
            total_pages = len(pdf.pages)
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                print(f"   Page {page_num}/{total_pages} extracted")
        
        final_text = text.strip()
        print(f"✅ Extracted {len(final_text)} characters from PDF")
        return final_text
    except Exception as e:
        print(f"❌ Error extracting PDF text: {e}")
        return ""


def summarize_resume(text: str) -> str:
    """Use OpenAI API to summarize the resume text."""
    if not text or len(text.strip()) < 50:
        return "No meaningful content found in resume."

    max_chars = 12000
    if len(text) > max_chars:
        text = text[:max_chars] + "..."
        print(f"⚠️  Resume truncated to {max_chars} characters")

    prompt = f"""Summarize this resume in 3-4 sentences covering:
1. Current role/most recent position
2. Key technical skills and expertise areas
3. Notable achievements or years of experience
4. Educational background (if mentioned)

Resume text:
{text}"""

    try:
        print("🤖 Generating resume summary with GPT-4...")
        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.7
        )
        summary = completion.choices[0].message.content.strip()
        print(f"✅ Summary generated ({len(summary)} chars)")
        return summary
    except Exception as e:
        print(f"❌ OpenAI API error: {e}")
        return f"Error generating summary: {str(e)}"


def update_persona_summary(persona_id: str, summary: str) -> bool:
    """Update the persona in Supabase with the resume summary."""
    try:
        response = supabase.table("personas").update({
            "resume_text": summary
        }).eq("id", persona_id).execute()
        
        print(f"✅ Updated persona {persona_id} with resume summary")
        return True
    except Exception as e:
        print(f"❌ Failed to update persona {persona_id}: {e}")
        return False


# ---------------- MAIN SCRIPT ----------------

def main():
    print("\n" + "="*70)
    print("🚀 RESUME PROCESSOR - Starting")
    print("="*70 + "\n")

    try:
        # Query personas with resume_url but no resume_text
        print("🔍 Querying database for unprocessed personas...")
        response = supabase.table("personas").select(
            "id, user_id, company_name, position, resume_url, resume_text"
        ).execute()
        
        # Filter for personas that need processing
        personas = [
            p for p in response.data 
            if p.get("resume_url") and (
                not p.get("resume_text") or 
                len(str(p.get("resume_text", "")).strip()) == 0
            )
        ] if response.data else []

        if not personas:
            print("✅ No unprocessed personas found. All resumes are up to date!")
            print("="*70 + "\n")
            return

        print(f"📋 Found {len(personas)} persona(s) to process\n")
        success_count = 0
        fail_count = 0

        for idx, persona in enumerate(personas, 1):
            print(f"\n{'─'*70}")
            print(f"[{idx}/{len(personas)}] Processing Persona")
            print(f"{'─'*70}")
            print(f"Company: {persona.get('company_name', 'Unknown')}")
            print(f"Position: {persona.get('position', 'Unknown')}")
            print(f"Persona ID: {persona['id']}")
            print(f"User ID: {persona.get('user_id', 'N/A')}")
            print()
            
            # Extract text from PDF
            text = fetch_pdf_text(persona["resume_url"])
            if not text or len(text.strip()) < 50:
                print("❌ No meaningful text extracted, skipping.\n")
                fail_count += 1
                continue

            # Generate summary
            summary = summarize_resume(text)
            if "Error" in summary:
                print("❌ Failed to generate summary\n")
                fail_count += 1
                continue

            # Update database
            if update_persona_summary(persona["id"], summary):
                success_count += 1
                print("✅ Successfully processed!\n")
            else:
                fail_count += 1
                print("❌ Failed to update database\n")

        print("\n" + "="*70)
        print("📊 PROCESSING COMPLETE")
        print("="*70)
        print(f"✅ Successfully processed: {success_count}")
        print(f"❌ Failed: {fail_count}")
        print(f"📈 Total: {success_count + fail_count}")
        print("="*70 + "\n")
        
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()