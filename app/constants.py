from enum import Enum


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"


class StreamType(Enum):
    CANDIDATE = "candidate"
    INTERVIEWER = "interviewer"
    AI_VOICE = "ai_voice"   # 🔊 NEW → mock interview AI speaker


# (optional but useful)
class InterviewMode(Enum):
    PRACTICE = "practice"
    MOCK = "mock"
