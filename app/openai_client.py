# app/openai_client.py

import os
import asyncio
from openai import OpenAI

# Load API key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize official client
client = OpenAI(api_key=OPENAI_API_KEY)

# Fallback model if requested model fails
DEFAULT_OPENAI_FALLBACK = "gpt-4o"


# ---------------------------------------------------------
# SAFE, ASYNC CHAT COMPLETION WRAPPER
# ---------------------------------------------------------
async def ask_openai(model: str, messages: list):
    """
    Async-safe wrapper for OpenAI ChatCompletion.
    - Runs blocking OpenAI SDK in a thread
    - Provides automatic fallback to DEFAULT_OPENAI_FALLBACK
    - Prevents crashes during high-load production use
    """

    try:
        # Sync OpenAI SDK call → run in background thread
        def run():
            return client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.6,
                max_tokens=800,
            )

        response = await asyncio.to_thread(run)
        return response.choices[0].message.content.strip()

    except Exception as e:
        error_msg = str(e)
        print(f"❌ OpenAI Error for model {model}: {error_msg}")

        # -------------------------------------------------
        # Automatic fallback to "gpt-4o"
        # -------------------------------------------------
        if model != DEFAULT_OPENAI_FALLBACK:
            try:
                print(f"⚠️ Falling back to {DEFAULT_OPENAI_FALLBACK}...")

                def fallback_run():
                    return client.chat.completions.create(
                        model=DEFAULT_OPENAI_FALLBACK,
                        messages=messages,
                        temperature=0.6,
                        max_tokens=800,
                    )

                fallback_response = await asyncio.to_thread(fallback_run)
                return fallback_response.choices[0].message.content.strip()

            except Exception as fe:
                # Fallback also failed — return detailed error
                return (
                    "OpenAI FATAL ERROR\n"
                    f"Original model failed: {model}\n"
                    f"Reason: {error_msg}\n\n"
                    f"Fallback model failed: {DEFAULT_OPENAI_FALLBACK}\n"
                    f"Reason: {str(fe)}"
                )

        # -------------------------------------------------
        # If the requested model *was already* the fallback
        # -------------------------------------------------
        return (
            "OpenAI ERROR: Request failed.\n"
            f"Model: {model}\n"
            f"Reason: {error_msg}"
        )


# ---------------------------------------------------------
# MODEL VALIDATION (Async + Non-blocking)
# ---------------------------------------------------------
async def validate_openai_models():
    """
    Fetches list of available OpenAI model IDs.
    - Runs synchronously in a thread to avoid blocking event loop
    - Returns list of model names
    - Falls back to a safe static list on failure
    """
    try:
        def run_models():
            return client.models.list()

        models_response = await asyncio.to_thread(run_models)

        # Convert to ["gpt-4o", "gpt-4o-mini", ...]
        return [m.id for m in models_response.data]

    except Exception as e:
        print("❌ Error validating OpenAI models:", e)

        # Hardcoded stable fallback list for system continuity
        return [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-3.1",
            "gpt-3.1-mini",
            "gpt-3.0",
            "gpt-3.0-mini",
        ]