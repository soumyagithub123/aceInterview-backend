from supabase import create_client, Client
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Supabase credentials (use service_role key here, NOT anon key)
SUPABASE_URL: str = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise ValueError("Supabase credentials are missing. Check .env file.")

# Create Supabase client (singleton)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# Bucket name (same as frontend)
RESUME_BUCKET = "resumes"

# Function for app.py to use
def get_supabase_client() -> Client:
    """Get the Supabase client instance"""
    return supabase