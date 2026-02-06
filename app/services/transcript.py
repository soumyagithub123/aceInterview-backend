# app/transcript.py
"""
OPTIMIZED - Better sentence completion detection
Fixes premature breaks in interviewer questions
"""

import time
from collections import deque
from difflib import SequenceMatcher
from typing import Optional


class TranscriptAccumulator:
    """
    Accumulates Deepgram transcripts and emits COMPLETE sentences
    
    KEY FIX: Longer pause threshold + better sentence detection
    Prevents breaking "What's your approach?" into multiple parts
    """

    def __init__(self, pause_threshold: float = 3.5):  # ⚡ INCREASED from 2.0 to 3.5
        self.pause_threshold = pause_threshold
        self.current_paragraph = ""
        self.last_speech_time = 0.0
        self.is_speaking = False

        # Recently completed transcripts for deduplication
        self.complete_paragraphs = deque(maxlen=50)

        # Minimum length to consider valid
        self.min_question_length = 10
        
        # ⚡ NEW: Track sentence completeness
        self.waiting_for_continuation = False

    def add_transcript(
        self,
        transcript: str,
        is_final: bool,
        speech_final: bool,
    ) -> Optional[str]:
        """
        Returns completed transcript when:
        - Deepgram marks speech_final AND sentence looks complete
        - OR enough silence passed (pause_threshold)
        """

        now = time.time()

        if not transcript or not transcript.strip():
            return None

        clean = transcript.strip()

        # --------------------------------------------------
        # FAST PATH: Deepgram finalized + looks complete
        # --------------------------------------------------
        if (is_final or speech_final) and len(clean) >= self.min_question_length:
            
            # ⚡ NEW: Check if sentence looks incomplete
            if self._looks_incomplete(clean):
                print(f"⏸️ Incomplete sentence, waiting: {clean[:50]}...")
                self.current_paragraph = clean
                self.last_speech_time = now
                self.is_speaking = True
                self.waiting_for_continuation = True
                return None
            
            # Sentence looks complete
            print(f"✅ Complete final transcript: {clean[:100]}...")

            self.current_paragraph = ""
            self.is_speaking = False
            self.waiting_for_continuation = False
            self.last_speech_time = now

            if not self._is_duplicate(clean):
                self.complete_paragraphs.append(clean.lower())
                return clean
            else:
                print(f"⭕ Duplicate skipped: {clean[:50]}...")
                return None

        # --------------------------------------------------
        # ACCUMULATE PARTIAL SEGMENTS
        # --------------------------------------------------
        if is_final or speech_final:
            if self.current_paragraph:
                # ⚡ Smart joining - check if continuation
                if self._is_continuation(self.current_paragraph, clean):
                    self.current_paragraph += " " + clean
                else:
                    # Different thought - replace
                    self.current_paragraph = clean
            else:
                self.current_paragraph = clean

            self.last_speech_time = now
            self.is_speaking = True

        # --------------------------------------------------
        # PAUSE-BASED COMPLETION
        # --------------------------------------------------
        if self.is_speaking and self.current_paragraph:
            elapsed = now - self.last_speech_time
            
            # ⚡ SMART PAUSE: Only complete if enough time OR sentence looks complete
            should_complete = False
            
            if elapsed >= self.pause_threshold:
                should_complete = True
            elif elapsed >= 1.5 and not self._looks_incomplete(self.current_paragraph):
                # Quick complete if sentence looks done (even before full pause)
                should_complete = True
            
            if should_complete:
                completed = self.current_paragraph.strip()

                self.current_paragraph = ""
                self.is_speaking = False
                self.waiting_for_continuation = False

                if len(completed) >= self.min_question_length:
                    if not self._is_duplicate(completed):
                        self.complete_paragraphs.append(completed.lower())
                        print(f"⏸️ Pause-complete transcript: {completed[:100]}...")
                        return completed

        return None

    # --------------------------------------------------
    # ⚡ NEW: SENTENCE COMPLETENESS DETECTION
    # --------------------------------------------------
    def _looks_incomplete(self, text: str) -> bool:
        """
        Check if sentence looks incomplete
        Helps prevent premature breaks
        """
        text = text.strip().lower()
        
        # Empty or too short
        if len(text) < 5:
            return True
        
        # Ends with incomplete patterns
        incomplete_endings = [
            "and", "or", "but", "so",  # Conjunctions
            "the", "a", "an",  # Articles
            "is", "are", "was", "were",  # Incomplete verbs
            "what's", "how's", "where's",  # Question starts
            "tell me", "explain", "describe",  # Incomplete requests
            "you", "your", "my",  # Incomplete references
        ]
        
        last_word = text.split()[-1] if text.split() else ""
        if last_word in incomplete_endings:
            return True
        
        # Very short questions without ending punctuation
        if len(text.split()) < 5 and not text.endswith(("?", ".", "!")):
            return True
        
        # Question words at end (incomplete question)
        if text.endswith(("what", "how", "why", "when", "where", "who")):
            return True
        
        return False
    
    def _is_continuation(self, previous: str, current: str) -> bool:
        """
        Check if current text is continuation of previous
        """
        prev_lower = previous.lower().strip()
        curr_lower = current.lower().strip()
        
        # Starts with continuation words
        continuation_starts = ["and", "or", "but", "so", "also", "then"]
        first_word = curr_lower.split()[0] if curr_lower.split() else ""
        
        if first_word in continuation_starts:
            return True
        
        # Similar topic (high word overlap)
        prev_words = set(prev_lower.split())
        curr_words = set(curr_lower.split())
        
        if len(prev_words.intersection(curr_words)) > 2:
            return True
        
        return False

    # --------------------------------------------------
    # RESET
    # --------------------------------------------------
    def reset(self):
        """Clear partial state"""
        self.current_paragraph = ""
        self.is_speaking = False
        self.last_speech_time = 0.0
        self.waiting_for_continuation = False
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
    # FORCE FLUSH
    # --------------------------------------------------
    def force_complete(self) -> Optional[str]:
        if (
            self.current_paragraph
            and len(self.current_paragraph) >= self.min_question_length
        ):
            completed = self.current_paragraph.strip()
            self.current_paragraph = ""
            self.is_speaking = False
            self.waiting_for_continuation = False
            print(f"⚠️ Force-complete: {completed[:100]}...")
            return completed
        return None