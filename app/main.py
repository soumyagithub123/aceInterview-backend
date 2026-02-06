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
# Import App Routes
# ---------------------------------------------------
from app.routes import (
    root,
    ws_dual_transcribe,
    models,
    manual_generate,
    persona,
    voice,
)

from app.ws import ws_live_interview

# ⭐ Payment router (inside app/payment/)
from app.payment.payment_server import router as payment_router

# Background worker
from app.resume_processor import process_unprocessed_resumes

# AI model availability loader
from app.ai_router import initialize_model_availability


# ---------------------------------------------------
# Create FastAPI App
# ---------------------------------------------------
app = FastAPI(
    title="Interview Assistant API",
    description="Real-time interview AI copilot backend with Mock Interview support",
    version="1.1.0"
)

# ---------------------------------------------------
# CORS
# ---------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------
# Register Routers
# ---------------------------------------------------
app.include_router(root.router)
app.include_router(ws_dual_transcribe.router)
app.include_router(ws_live_interview.router)
app.include_router(models.router)
app.include_router(manual_generate.router)
app.include_router(persona.router)

# 🔊 AI VOICE ROUTES (Updated with Mock Interview)
app.include_router(voice.router)  

# ⭐ PAYMENT ROUTES
app.include_router(payment_router)


# ---------------------------------------------------
# Startup Tasks
# ---------------------------------------------------
@app.on_event("startup")
async def startup_event():
    print("🔄 Launching background resume processor…")
    asyncio.create_task(process_unprocessed_resumes())
    print("✅ Resume processor running in background")

    print("🔍 Checking and caching AI model availability…")
    await initialize_model_availability()
    print("✅ Model availability cached (OpenAI + Gemini)")
    
    print("\n" + "=" * 80)
    print("🎤 MOCK INTERVIEW MODULE LOADED")
    print("   - AI Question Generation: ✅")
    print("   - Voice Integration: ✅")
    print("   - WebSocket Support: ✅")
    print("=" * 80 + "\n")


# ---------------------------------------------------
# Uvicorn Server
# ---------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 10000))

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
        reload=True
    )