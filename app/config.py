import os
from dotenv import load_dotenv

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

DEFAULT_MODEL = "gpt-4o-mini"
KEEPALIVE_INTERVAL = 5
RENDER_KEEPALIVE = 30
