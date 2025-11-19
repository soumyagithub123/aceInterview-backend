from fastapi import APIRouter

from app.config import DEEPGRAM_API_KEY, OPENAI_API_KEY, DEFAULT_MODEL



router = APIRouter()



@router.get("/")

async def root():

    return {

        "status": "running",

        "service": "Interview Assistant API",

        "version": "1.0.0",

        "websockets_version": "14.1",

        "docs": "/docs",

        "health": "/health"

    }



@router.get("/health")

async def health_check():

    return {

        "status": "healthy",

        "message": "Interview Assistant API - Render Compatible",

        "audio_capture": "browser-based",

        "server_audio": "not required",

        "deepgram": "configured" if DEEPGRAM_API_KEY else "missing",

        "openai": "configured" if OPENAI_API_KEY else "missing",

        "websockets_version": "14.1"

    }



@router.get("/api/models/status")

async def get_model_status():

    return {

        "default_provider": DEFAULT_MODEL,

        "available_providers": {"gpt-4o-mini": True, "gpt-4o": True}

    }