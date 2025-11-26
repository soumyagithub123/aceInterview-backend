import sys
import asyncio
import os

# ---------------------------------------------------
# Ensure UTF-8 logs (Windows-safe)
# ---------------------------------------------------
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

print("=" * 80)
print("🚀 STARTING INTERVIEW ASSISTANT BACKEND")
print("=" * 80)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------
# Import All Routes
# ---------------------------------------------------
from app.routes import (
    root,
    ws_dual_transcribe,
    ws_live_interview,
    models,
    manual_generate,
    persona,            # ⭐ FIX: Added persona API router
)

# Background worker
from app.resume_processor import process_unprocessed_resumes

# AI model availability loader
from app.ai_router import initialize_model_availability


# ---------------------------------------------------
# Create FastAPI Application
# ---------------------------------------------------
app = FastAPI(
    title="Interview Assistant API",
    description="Real-time interview AI copilot backend",
    version="1.0.0"
)

# ---------------------------------------------------
# CORS CONFIG (Frontend Will Work Without Issues)
# ---------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # Allow frontend dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------
# Register API Routes
# ---------------------------------------------------
app.include_router(root.router)
app.include_router(ws_dual_transcribe.router)
app.include_router(ws_live_interview.router)
app.include_router(models.router)
app.include_router(manual_generate.router)
app.include_router(persona.router)           # ⭐ FIXED: persona API now works


# ---------------------------------------------------
# Startup: Background Tasks + AI Model Preload
# ---------------------------------------------------
@app.on_event("startup")
async def startup_event():
    print("🔄 Launching background resume processor…")
    asyncio.create_task(process_unprocessed_resumes())
    print("✅ Resume processor running in background")

    print("🔍 Checking and caching AI model availability…")
    await initialize_model_availability()
    print("✅ Model availability cached (OpenAI + Gemini)")


# ---------------------------------------------------
# Local Development Server
# ---------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))

    print("\n" + "=" * 80)
    print("🚀 STARTING DEVELOPMENT SERVER")
    print("=" * 80)
    print(f"Host:              0.0.0.0")
    print(f"Port:              {port}")
    print(f"Deepgram Key:      {'✅ present' if os.getenv('DEEPGRAM_API_KEY') else '❌ missing'}")
    print(f"OpenAI Key:        {'✅ present' if os.getenv('OPENAI_API_KEY') else '❌ missing'}")
    print(f"Gemini Key:        {'✅ present' if os.getenv('GEMINI_API_KEY') else '❌ missing'}")
    print("=" * 80)

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True,
        timeout_keep_alive=75,
        reload=True                       # 🔥 Auto restart on changes (dev-only)
    )
