# app/ai_router.py
import asyncio
from typing import List, Dict

from app.client.openai_client import ask_openai, validate_openai_models
from app.client.gemini_client import ask_gemini, validate_gemini_models

# Cached after startup
AVAILABLE_OPENAI_MODELS = set()
AVAILABLE_GEMINI_MODELS = set()


# ---------------------------------------------------------
# Initialize model availability at FastAPI startup
# ---------------------------------------------------------
async def initialize_model_availability():
    """
    Loads and caches available models from OpenAI and Gemini.
    Ensures the entire system knows exactly which models 
    are callable before any request reaches ask_ai().
    """
    global AVAILABLE_OPENAI_MODELS, AVAILABLE_GEMINI_MODELS

    try:
        print("🔍 Fetching OpenAI models...")
        AVAILABLE_OPENAI_MODELS = set(await validate_openai_models())
        print("✅ OpenAI Models Loaded:", AVAILABLE_OPENAI_MODELS)
    except Exception as e:
        print("❌ Failed loading OpenAI models:", e)
        AVAILABLE_OPENAI_MODELS = set()

    try:
        print("🔍 Fetching Gemini models...")
        AVAILABLE_GEMINI_MODELS = set(await validate_gemini_models())
        print("✅ Gemini Models Loaded:", AVAILABLE_GEMINI_MODELS)
    except Exception as e:
        print("❌ Failed loading Gemini models:", e)
        AVAILABLE_GEMINI_MODELS = set()

    print("\n🔥 FINAL MODEL AVAILABILITY STATE:")
    print("   OpenAI:", AVAILABLE_OPENAI_MODELS)
    print("   Gemini:", AVAILABLE_GEMINI_MODELS)
    print("-----------------------------------------------------\n")


# ---------------------------------------------------------
# Normalize incoming model names
# ---------------------------------------------------------
def normalize_model(model: str) -> str:
    """
    Normalize model names safely and consistently.
    Always lowercase and strip whitespace.
    """
    if not model or not isinstance(model, str):
        return "gpt-4o"  # safe default
    return model.lower().strip()


# ---------------------------------------------------------
# Check if model is available
# ---------------------------------------------------------
def is_model_available(model: str) -> bool:
    """
    Checks whether the model exists in either OpenAI
    or Gemini validated model lists.
    """
    model = normalize_model(model)

    if model.startswith("gpt"):
        return model in AVAILABLE_OPENAI_MODELS

    if model.startswith("gemini"):
        return model in AVAILABLE_GEMINI_MODELS

    return False


# ---------------------------------------------------------
# Central AI Request Router
# ---------------------------------------------------------
async def ask_ai(model: str, messages: List[Dict]):
    """
    Primary AI router for the entire backend.

    - Normalizes model name
    - Verifies model is available
    - Routes request to correct provider (OpenAI or Gemini)
    - Returns AI-generated text or a human-readable error
    """
    model = normalize_model(model)

    # 1. Availability Check
    if not is_model_available(model):
        return (
            "AI ERROR: Requested model is not available.\n"
            f"Requested: {model}\n"
            "Check model settings or available models list."
        )

    # 2. Dispatch to provider
    try:
        # ----------------------
        # OpenAI / GPT
        # ----------------------
        if model.startswith("gpt"):
            print(f"🤖 Routing → OpenAI ({model})")
            return await ask_openai(model, messages)

        # ----------------------
        # Google Gemini
        # ----------------------
        if model.startswith("gemini"):
            print(f"🌟 Routing → Gemini ({model})")
            return await ask_gemini(model, messages)

        # ----------------------
        # Unknown Provider
        # ----------------------
        return (
            "AI ERROR: Unsupported model provider.\n"
            f"Model: {model}\n"
            "Supported: OpenAI GPT (gpt-*), Google Gemini (gemini-*)"
        )

    except Exception as e:
        # 3. Unified error catch
        return (
            "AI ERROR: Model processing failed.\n"
            f"Model: {model}\n"
            f"Reason: {str(e)}"
        )