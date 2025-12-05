import time
from collections import deque
from difflib import SequenceMatcher
from typing import Optional

class TranscriptAccumulator:
    def __init__(self, pause_threshold: float = 2.0):
        self.pause_threshold = pause_threshold
        self.current_paragraph = ""
        self.last_speech_time = 0
        self.is_speaking = False
        self.complete_paragraphs = deque(maxlen=50)
        self.min_question_length = 10

    def add_transcript(self, transcript: str, is_final: bool, speech_final: bool) -> Optional[str]:
        current_time = time.time()
        if not transcript or not transcript.strip():
            return None
        if (is_final or speech_final) and len(transcript.strip()) >= self.min_question_length:
            print(f"✅ Processing complete transcript immediately: {transcript[:100]}...")
            if not self._is_duplicate(transcript.strip()):
                self.complete_paragraphs.append(transcript.strip().lower())
                return transcript.strip()
            else:
                print(f"⏭️ Skipping duplicate: {transcript[:50]}...")
                return None
        if is_final or speech_final:
            if self.current_paragraph:
                self.current_paragraph += " " + transcript.strip()
            else:
                self.current_paragraph = transcript.strip()
            self.last_speech_time = current_time
            self.is_speaking = True
        if self.is_speaking and self.current_paragraph:
            time_since_last_speech = current_time - self.last_speech_time
            if time_since_last_speech >= self.pause_threshold:
                complete_text = self.current_paragraph.strip()
                if len(complete_text) >= self.min_question_length:
                    if not self._is_duplicate(complete_text):
                        self.complete_paragraphs.append(complete_text.lower())
                        self.current_paragraph = ""
                        self.is_speaking = False
                        return complete_text
                self.current_paragraph = ""
                self.is_speaking = False
        return None

    def _is_duplicate(self, text: str, threshold: float = 0.85) -> bool:
        text_lower = text.lower().strip()
        for prev in self.complete_paragraphs:
            similarity = SequenceMatcher(None, text_lower, prev).ratio()
            if similarity > threshold:
                return True
        return False

    def force_complete(self) -> Optional[str]:
        if self.current_paragraph and len(self.current_paragraph) >= self.min_question_length:
            complete_text = self.current_paragraph.strip()
            self.current_paragraph = ""
            self.is_speaking = False
            return complete_text
        return None
