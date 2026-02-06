import base64
from openai import OpenAI
from app.config import OPENAI_TTS_API_KEY

# ✅ CORRECT OpenAI TTS MODEL (tts-1 or tts-1-hd)
DEFAULT_TTS_MODEL = "tts-1"  # Fast, good quality
# Alternative: "tts-1-hd" for higher quality (slower)

DEFAULT_VOICE = "alloy"

client = OpenAI(api_key=OPENAI_TTS_API_KEY)


def text_to_speech_base64(
    text: str,
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_TTS_MODEL,
    audio_format: str = "mp3",
) -> str:
    """
    Convert text to speech using OpenAI TTS
    
    Args:
        text: Text to convert
        voice: alloy, echo, fable, onyx, nova, shimmer
        model: tts-1 (fast) or tts-1-hd (high quality)
        audio_format: mp3, opus, aac, flac
    
    Returns:
        Base64 encoded audio string
    """
    if not text or not text.strip():
        return ""
    
    if not OPENAI_TTS_API_KEY:
        print("❌ OPENAI_TTS_API_KEY not configured")
        return ""

    try:
        # ✅ CORRECT OpenAI TTS API call
        with client.audio.speech.with_streaming_response.create(
            model=model,
            voice=voice,
            input=text,
            response_format=audio_format,  # ✅ Use response_format instead of format
        ) as response:
            audio_bytes = response.read()

        return base64.b64encode(audio_bytes).decode("utf-8")
    
    except Exception as e:
        print(f"❌ TTS Error: {e}")
        return ""