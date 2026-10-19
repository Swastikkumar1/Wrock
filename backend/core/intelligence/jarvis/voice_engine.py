from dataclasses import dataclass
from typing import Optional, Callable, Dict, Any
import time

@dataclass
class AudioState:
    is_listening: bool = False
    is_speaking: bool = False
    wake_word_detected: bool = False
    active_transcript: str = ""
    last_completed_utterance: str = ""
    confidence: float = 0.0
    timestamp: float = 0.0

class VoiceEngine:
    """
    Voice engine adapting hotword detection, live streaming ASR
    state tracking, and TTS audio queuing for Wrock.
    """

    def __init__(self, wake_word: str = "wrock"):
        self.wake_word = wake_word.lower()
        self.state = AudioState()
        self._on_wake_detected: Optional[Callable[[], None]] = None
        self._on_command_ready: Optional[Callable[[str], None]] = None

    def process_incoming_transcript(self, raw_transcript: str, is_final: bool = False) -> Dict[str, Any]:
        """
        Processes real-time ASR text streaming from client or local STT.
        Checks for Wrock wake-word triggers and command boundaries.
        """
        text = raw_transcript.strip()
        lower_text = text.lower()
        now = time.time()

        self.state.active_transcript = text
        self.state.timestamp = now

        # Wake-word detection check (wrock, rock, hey wrock, hey rock, jarvis)
        import re
        wake_pattern = r"\b(wrock|rock|brok|jarvis)\b"
        if re.search(wake_pattern, lower_text):
            self.state.wake_word_detected = True
            self.state.is_listening = True
            # Strip wake word for cleaner intent extraction
            cleaned_command = re.sub(r"^(hey\s+)?(wrock|rock|brok|jarvis)\b[,:\s]*", "", lower_text).strip(" ,:.-")
        else:
            cleaned_command = lower_text

        if is_final and text:
            self.state.last_completed_utterance = cleaned_command or text
            self.state.is_listening = False
            self.state.wake_word_detected = False

            return {
                "triggered": True,
                "command": self.state.last_completed_utterance,
                "raw": text,
                "timestamp": now,
            }

        return {
            "triggered": False,
            "partial": text,
            "wake_active": self.state.wake_word_detected,
        }

    def set_speaking(self, is_speaking: bool) -> None:
        self.state.is_speaking = is_speaking

    def get_state(self) -> Dict[str, Any]:
        return {
            "is_listening": self.state.is_listening,
            "is_speaking": self.state.is_speaking,
            "wake_word_detected": self.state.wake_word_detected,
            "active_transcript": self.state.active_transcript,
            "last_completed_utterance": self.state.last_completed_utterance,
        }
