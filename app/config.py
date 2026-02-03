import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Keys
DEEPGRAM_API_KEY   = os.getenv("DEEPGRAM_API_KEY")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")        # Chat / text
OPENAI_TTS_API_KEY = os.getenv("OPENAI_TTS_API_KEY")    # 🔊 Voice / TTS
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY")

# Deprecated — model comes from Supabase now
DEFAULT_MODEL = None    # Keep for compatibility but NOT used

# WebSocket Keepalive values
KEEPALIVE_INTERVAL = 5
RENDER_KEEPALIVE   = 30


# Optional: validate keys for debugging (not required)
def validate_config():
    if not DEEPGRAM_API_KEY:
        print("⚠ WARNING: DEEPGRAM_API_KEY missing")
    if not OPENAI_API_KEY:
        print("⚠ WARNING: OPENAI_API_KEY missing")
    if not OPENAI_TTS_API_KEY:
        print("⚠ WARNING: OPENAI_TTS_API_KEY missing (voice disabled)")
    if not GEMINI_API_KEY:
        print("⚠ WARNING: GEMINI_API_KEY missing")
