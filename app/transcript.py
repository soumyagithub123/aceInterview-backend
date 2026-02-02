# app/transcript.py

import time
from collections import deque
from difflib import SequenceMatcher
from typing import Optional


class TranscriptAccumulator:
    """
    Accumulates Deepgram transcripts and emits a CLEAN, FINAL transcript
    when speech is complete (pause or speech_final).

    - Filters duplicates
    - Ignores short/noisy utterances
    - Prevents repeated routing to AI
    - Supports explicit reset between interviewer questions
    """

    def __init__(self, pause_threshold: float = 2.0):
        self.pause_threshold = pause_threshold
        self.current_paragraph = ""
        self.last_speech_time = 0.0
        self.is_speaking = False

        # Store recently completed transcripts (lowercased) for de-duplication
        self.complete_paragraphs = deque(maxlen=50)

        # Minimum length to consider something a valid utterance
        self.min_question_length = 10

    # --------------------------------------------------
    # MAIN ENTRY POINT
    # --------------------------------------------------
    def add_transcript(
        self,
        transcript: str,
        is_final: bool,
        speech_final: bool,
    ) -> Optional[str]:
        """
        Returns a completed transcript ONLY when:
        - Deepgram marks it final, OR
        - Enough silence has passed (pause_threshold)

        Otherwise returns None.
        """

        now = time.time()

        if not transcript or not transcript.strip():
            return None

        clean = transcript.strip()

        # --------------------------------------------------
        # FAST PATH: Deepgram already finalized this segment
        # --------------------------------------------------
        if (is_final or speech_final) and len(clean) >= self.min_question_length:
            print(f"✅ Immediate final transcript: {clean[:100]}...")

            # IMPORTANT: clear any partial state to prevent leakage
            self.current_paragraph = ""
            self.is_speaking = False
            self.last_speech_time = now

            if not self._is_duplicate(clean):
                self.complete_paragraphs.append(clean.lower())
                return clean
            else:
                print(f"⏭️ Duplicate skipped: {clean[:50]}...")
                return None

        # --------------------------------------------------
        # ACCUMULATE PARTIAL SEGMENTS
        # --------------------------------------------------
        if is_final or speech_final:
            if self.current_paragraph:
                self.current_paragraph += " " + clean
            else:
                self.current_paragraph = clean

            self.last_speech_time = now
            self.is_speaking = True

        # --------------------------------------------------
        # PAUSE-BASED COMPLETION
        # --------------------------------------------------
        if self.is_speaking and self.current_paragraph:
            if now - self.last_speech_time >= self.pause_threshold:
                completed = self.current_paragraph.strip()

                self.current_paragraph = ""
                self.is_speaking = False

                if len(completed) >= self.min_question_length:
                    if not self._is_duplicate(completed):
                        self.complete_paragraphs.append(completed.lower())
                        print(f"⏸️ Pause-complete transcript: {completed[:100]}...")
                        return completed

        return None

    # --------------------------------------------------
    # RESET (CRITICAL FOR SESSION FLOW)
    # --------------------------------------------------
    def reset(self):
        """
        Explicitly clears partial state.
        Used when a new interviewer question cycle starts.
        """
        self.current_paragraph = ""
        self.is_speaking = False
        self.last_speech_time = 0.0
        print("🔄 TranscriptAccumulator reset")

    # --------------------------------------------------
    # DUPLICATE DETECTION
    # --------------------------------------------------
    def _is_duplicate(self, text: str, threshold: float = 0.85) -> bool:
        text_lower = text.lower().strip()
        for prev in self.complete_paragraphs:
            if SequenceMatcher(None, text_lower, prev).ratio() > threshold:
                return True
        return False

    # --------------------------------------------------
    # FORCE FLUSH (RARE / SAFETY)
    # --------------------------------------------------
    def force_complete(self) -> Optional[str]:
        if (
            self.current_paragraph
            and len(self.current_paragraph) >= self.min_question_length
        ):
            completed = self.current_paragraph.strip()
            self.current_paragraph = ""
            self.is_speaking = False
            print(f"⚠️ Force-complete transcript: {completed[:100]}...")
            return completed
        return None
