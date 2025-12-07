# app/gemini_client.py

import os
import asyncio
import google.generativeai as genai

# Load API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# Allowed short models
GEMINI_MODEL_WHITELIST = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-pro",
]

DEFAULT_GEMINI_FALLBACK = "gemini-2.0-flash"



# ---------------------------------------------------------
# Convert short → full model names
# ---------------------------------------------------------
def normalize_gemini_model(model: str):
    """Gemini now requires full IDs: models/<name>"""
    model = model.strip()
    if model.startswith("models/"):
        return model
    return f"models/{model}"


# ---------------------------------------------------------
# Extract clean text from Gemini responses
# ---------------------------------------------------------
def extract_gemini_text(response):
    if hasattr(response, "text") and response.text:
        return response.text

    try:
        if response.candidates:
            parts = response.candidates[0].content.parts
            combined = "".join(p.text for p in parts if hasattr(p, "text"))
            if combined.strip():
                return combined
    except:
        pass

    return "Gemini returned an empty or unrecognized response format."


# ---------------------------------------------------------
# Model discovery
# ---------------------------------------------------------
async def get_available_gemini_models():
    try:
        def run_list():
            return genai.list_models()

        models = await asyncio.to_thread(run_list)
        available = [
            m.name.split("/")[-1]
            for m in models
            if "generateContent" in getattr(m, "supported_generation_methods", [])
        ]
        return available

    except Exception as e:
        print(f"❌ Error fetching Gemini model list: {e}")
        return [DEFAULT_GEMINI_FALLBACK]


async def validate_gemini_models():
    models = await get_available_gemini_models()
    return [m for m in GEMINI_MODEL_WHITELIST if m in models]


# ---------------------------------------------------------
# Main Gemini Wrapper
# ---------------------------------------------------------
async def ask_gemini(model: str, messages: list):
    model = (model or DEFAULT_GEMINI_FALLBACK).strip()
    full_model = normalize_gemini_model(model)

    # Convert OpenAI messages → plain text
    prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)

    try:
        def call():
            instance = genai.GenerativeModel(full_model)
            return instance.generate_content(prompt)

        response = await asyncio.to_thread(call)
        return extract_gemini_text(response).strip()

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Gemini error for {model} → {error_msg}")

        if model != DEFAULT_GEMINI_FALLBACK:
            try:
                fallback_full = normalize_gemini_model(DEFAULT_GEMINI_FALLBACK)

                def fb():
                    instance = genai.GenerativeModel(fallback_full)
                    return instance.generate_content(prompt)

                fb_response = await asyncio.to_thread(fb)
                return extract_gemini_text(fb_response).strip()

            except Exception as fe:
                return (
                    "Gemini FATAL ERROR:\n"
                    f"Original model failed: {model} ({error_msg})\n"
                    f"Fallback failed: {DEFAULT_GEMINI_FALLBACK} ({str(fe)})"
                )

        return (
            "Gemini ERROR: Request failed.\n"
            f"Model: {model}\n"
            f"Reason: {error_msg}"
        )