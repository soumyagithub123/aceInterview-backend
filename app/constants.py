from enum import Enum

class ConnectionState(Enum):
	DISCONNECTED = "disconnected"
	CONNECTING = "connecting"
	CONNECTED = "connected"
	DISCONNECTING = "disconnecting"

class StreamType(Enum):
	CANDIDATE = "candidate"
	INTERVIEWER = "interviewer"