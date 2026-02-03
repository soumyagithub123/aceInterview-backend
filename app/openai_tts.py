import base64
from openai import OpenAI
from app.config import OPENAI_TTS_API_KEY

DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_VOICE = "alloy"

client = OpenAI(api_key=OPENAI_TTS_API_KEY)


def text_to_speech_base64(
    text: str,
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_TTS_MODEL,
    audio_format: str = "mp3",
) -> str:
    if not text or not text.strip():
        return ""

    # ✅ CORRECT OpenAI TTS CALL
    with client.audio.speech.with_streaming_response.create(
        model=model,
        voice=voice,
        input=text,
        format=audio_format,
    ) as response:
        audio_bytes = response.read()

    return base64.b64encode(audio_bytes).decode("utf-8")
