import sys

# Ensure UTF-8 encoding for stdout and stderr
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

print("=" * 70)
print("🚀 STARTING INTERVIEW ASSISTANT BACKEND")
print("=" * 70)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

# Import your app's routers, assuming they are defined in `app.routes`
from app.routes import root, ws_dual_transcribe, ws_live_interview

# Create FastAPI app
app = FastAPI(title="Interview Assistant API - Render Compatible")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include route modules
app.include_router(root.router)
app.include_router(ws_dual_transcribe.router)
app.include_router(ws_live_interview.router)

# Run server if this script is executed directly
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    print("\n" + "=" * 70)
    print("🚀 STARTING SERVER")
    print("=" * 70)
    print(f"Port: {port}")
    print(f"Host: 0.0.0.0")
    print(f"Websockets: 14.1 (additional_headers compatible)")
    print(f"Deepgram: {'✅ Configured' if os.getenv('DEEPGRAM_API_KEY') else '❌ Missing'}")
    print(f"OpenAI: {'✅ Configured' if os.getenv('OPENAI_API_KEY') else '❌ Missing'}")
    print("=" * 70)

    # Launch server
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True,
        timeout_keep_alive=75
    )
