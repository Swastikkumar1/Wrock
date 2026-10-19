import asyncio
import os
import sys
import re
import time
import logging
from enum import Enum
from typing import Dict, Any, Optional, Callable, Awaitable

_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

try:
    from backend.config import settings
except ImportError:
    from config import settings

from .tts import ElevenLabsTTSClient

logger = logging.getLogger("AssistantLifecycle")


class LifecycleState(str, Enum):
    SLEEPING = "SLEEPING"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"


class CancellationToken:
    """
    Thread-safe cancellation token to instantly abort audio streaming,
    TTS playback, or ongoing background assistant tasks.
    """

    def __init__(self):
        self._is_cancelled: bool = False

    @property
    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def cancel(self):
        self._is_cancelled = True

    def reset(self):
        self._is_cancelled = False


class AssistantLifecycle:
    """
    Non-blocking conversational lifecycle manager.
    Handles:
    - Strict 'Wake up Wrock' initiation.
    - Persistent live session with idle timeout and dismiss commands.
    - Zero-latency barge-in speech interruption.
    - Decoupled asynchronous tool execution.
    - Minimalist, functional persona responses with zero boilerplate fluff.
    """

    def __init__(
        self,
        intent_router=None,
        tts_client: Optional[ElevenLabsTTSClient] = None,
        broadcast_callback: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None,
    ):
        self.intent_router = intent_router
        self.tts_client = tts_client or ElevenLabsTTSClient()
        self.broadcast_callback = broadcast_callback

        # State
        self.state: LifecycleState = LifecycleState.SLEEPING
        self.cancellation_token = CancellationToken()
        self.last_user_activity: float = time.time()
        self.active_execution_task: Optional[asyncio.Task] = None

        # Debounce state to prevent duplicate rapid executions
        self._last_executed_cmd: str = ""
        self._last_executed_time: float = 0.0

        # Barge-in keywords
        self.interrupt_words = {"stop", "cancel", "quiet", "hold on", "pause", "shut up", "silence", "wait"}

        # Dismiss keywords
        self.dismiss_patterns = [
            r"\bgo to sleep\b",
            r"\bsleep\b",
            r"\bdismiss\b",
            r"\bstand by\b",
            r"\bstandby\b",
            r"\bstop listening\b",
            r"\bgoodbye\b",
        ]

    # -------------------------------------------------------------
    # State & Event Broadcasting
    # -------------------------------------------------------------
    async def set_state(self, new_state: LifecycleState):
        prev = self.state
        self.state = new_state
        if prev != new_state:
            logger.info(f"Lifecycle state transition: {prev.value} -> {new_state.value}")
            await self._broadcast("LIFECYCLE_STATE", {
                "state": self.state.value,
                "is_awake": self.state != LifecycleState.SLEEPING,
            })

    async def _broadcast(self, event_type: str, payload: Dict[str, Any]):
        if self.broadcast_callback:
            try:
                await self.broadcast_callback(event_type, payload)
            except Exception as e:
                logger.debug(f"Broadcast error: {e}")

    # -------------------------------------------------------------
    # 1. Instant Speech Interruption ("Barge-In")
    # -------------------------------------------------------------
    async def interrupt_speech(self, reason: str = "barge_in"):
        """
        Immediately aborts audio playback, cancels current TTS,
        and transitions state back to LISTENING.
        """
        logger.info(f"Barge-in speech interruption triggered: {reason}")
        self.cancellation_token.cancel()

        # Notify clients to instantly stop audio playback & flush buffers
        await self._broadcast("SPEECH_INTERRUPTED", {
            "reason": reason,
            "timestamp": time.time(),
        })

        if self.state == LifecycleState.SPEAKING:
            await self.set_state(LifecycleState.LISTENING)

    # -------------------------------------------------------------
    # 2. Incoming Speech & Transcript Processing
    # -------------------------------------------------------------
    async def handle_user_transcript(
        self,
        transcript: str,
        is_final: bool,
        perception_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        raw_text = transcript.strip()
        if not raw_text:
            return None

        lower_text = raw_text.lower()
        now = time.time()

        # Check for instant barge-in if assistant is actively speaking
        if self.state == LifecycleState.SPEAKING:
            is_interrupt_phrase = any(w in lower_text.split() for w in self.interrupt_words)
            # Interrupt on either an explicit interrupt word or any new command input
            await self.interrupt_speech(reason="user_speaking")

            if is_interrupt_phrase:
                # User just wanted Wrock to stop talking
                await self.set_state(LifecycleState.LISTENING)
                return {"action": "interrupted", "text": "Stopped."}

        # Check idle timeout if active (only if idle_timeout > 0)
        if self.state != LifecycleState.SLEEPING:
            idle_timeout = getattr(settings, "VOICE_IDLE_TIMEOUT_SEC", 0.0)
            if idle_timeout > 0 and (now - self.last_user_activity) > idle_timeout:
                logger.info(f"Session idle timeout ({idle_timeout}s). Returning to SLEEPING.")
                await self.dismiss()
                return None

        # ---------------------------------------------------------
        # A. Sleeping State: Wake-Phrase Required
        # Matches "wake up", "wake up block", "wake up wrock", "hey wrock", etc.
        # ---------------------------------------------------------
        if self.state == LifecycleState.SLEEPING:
            wake_regex = r"\b(?:wake\s+up(?:\s+(?:wrock|rock|brok|block|lock|work|doc|buddy|jarvis))?|(?:hey|hi|hello|ok|okay)\s+(?:wrock|rock|brok|block|jarvis))\b"
            is_wake = bool(re.search(wake_regex, lower_text))

            if is_wake:
                await self.wake_up()
                command_after_wake = re.sub(wake_regex + r"[,:\s]*", "", lower_text).strip()

                if command_after_wake and is_final:
                    return await self.execute_command(command_after_wake, perception_snapshot)
                return {"action": "woken", "reply": "Yes, I am online. What's your command, Swastik?"}
            else:
                # Discard all ambient speech when sleeping
                return None

        # ---------------------------------------------------------
        # B. Active State: Process Commands Direct & Check Dismiss
        # ---------------------------------------------------------
        self.last_user_activity = now

        # Check explicit dismiss commands
        for pattern in self.dismiss_patterns:
            if re.search(pattern, lower_text):
                await self.dismiss()
                return {"action": "dismissed", "reply": "Standing by."}

        if not is_final:
            return None

        # Strip optional wake phrase prefix if user happened to repeat it
        cleaned_cmd = re.sub(r"^(hey\s+)?(wake\s+up\s+)?(wrock|rock|brok|block|jarvis)\b[,:\s]*", "", lower_text).strip()
        final_cmd = cleaned_cmd or lower_text

        return await self.execute_command(final_cmd, perception_snapshot)

    # -------------------------------------------------------------
    # 3. Activation & Conversational Conciseness
    # -------------------------------------------------------------
    async def wake_up(self, silent: bool = False):
        """
        Initiates the assistant with clear, personalized confirmation.
        Responds: "Yes, I am online. What's your command, Swastik?"
        """
        logger.info("Wrock initiated via wake trigger.")
        self.cancellation_token.reset()
        self.last_user_activity = time.time()
        await self.set_state(LifecycleState.LISTENING)

        if not silent:
            reply_text = "Yes, I am online. What's your command, Swastik?"
            await self.speak_direct(reply_text, play_wake_chime=True)

    async def dismiss(self):
        """
        Transitions to SLEEPING on idle timeout or explicit command.
        """
        logger.info("Wrock dismissed. Entering SLEEPING state.")
        self.cancellation_token.cancel()
        await self.speak_direct("Standing by.")
        await self.set_state(LifecycleState.SLEEPING)

    # -------------------------------------------------------------
    # 4. Decoupled Asynchronous Tool Execution
    # -------------------------------------------------------------
    async def execute_command(
        self,
        command_text: str,
        perception_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes user command asynchronously without blocking voice or telemetry loops.
        """
        if not command_text.strip():
            return {"action": "none"}

        now = time.time()
        norm_cmd = command_text.strip().lower()
        if norm_cmd == self._last_executed_cmd and (now - self._last_executed_time) < 2.0:
            logger.info(f"Debounce: Ignoring duplicate execution of '{command_text}' within 2.0s window.")
            return {"action": "debounced"}
        self._last_executed_cmd = norm_cmd
        self._last_executed_time = now

        self.last_user_activity = now
        await self.set_state(LifecycleState.THINKING)
        self.cancellation_token.reset()

        logger.info(f"Asynchronous tool execution initiated for: '{command_text}'")

        snapshot = perception_snapshot or {}

        # Run routing and execution in background task
        async def _run_async_tool():
            try:
                if self.intent_router:
                    intent_resp = await self.intent_router.route_intent(command_text, snapshot)
                    spoken_reply = self._clean_reply(intent_resp.spoken_text)

                    # Check cancellation before speaking
                    if not self.cancellation_token.is_cancelled and spoken_reply:
                        await self.speak_direct(spoken_reply)

                    # Broadcast intent results
                    await self._broadcast("VOICE_INTENT", {
                        "spoken_text": spoken_reply,
                        "hud_alert": intent_resp.hud_alert or spoken_reply,
                        "target_entity_id": intent_resp.target_entity_id,
                        "camera_mode": intent_resp.camera_mode,
                        "pov_entity_id": intent_resp.pov_entity_id,
                        "action_type": intent_resp.action_type,
                        "tools_called": [t.tool_name for t in intent_resp.tool_results],
                    })

                    return intent_resp
                else:
                    fallback_reply = f"Executed: {command_text}."
                    await self.speak_direct(fallback_reply)
                    return {"output": fallback_reply}
            except asyncio.CancelledError:
                logger.info(f"Task for '{command_text}' cancelled.")
            except Exception as e:
                logger.error(f"Error executing command '{command_text}': {e}", exc_info=True)
                await self.speak_direct("Error executing action.")
            finally:
                if self.state == LifecycleState.THINKING:
                    await self.set_state(LifecycleState.LISTENING)

        self.active_execution_task = asyncio.create_task(_run_async_tool())
        return {"action": "dispatched", "command": command_text}

    # -------------------------------------------------------------
    # 5. Non-Blocking TTS Speech Output (ElevenLabs + Web Speech)
    # -------------------------------------------------------------
    async def speak_direct(self, text: str, play_wake_chime: bool = False):
        """
        Non-blocking speech output. Supports ElevenLabs audio streaming / base64
        and triggers client TTS with cancellation support.
        """
        if not text.strip() or self.cancellation_token.is_cancelled:
            return

        cleaned_text = self._clean_reply(text)
        await self.set_state(LifecycleState.SPEAKING)

        # Attempt high-quality ElevenLabs generation asynchronously
        audio_b64 = None
        try:
            audio_b64 = await self.tts_client.generate_speech_base64(cleaned_text, self.cancellation_token)
        except Exception as e:
            logger.debug(f"ElevenLabs TTS generation skipped: {e}")

        # Broadcast speech payload to HUD
        await self._broadcast("ASSISTANT_SPEECH", {
            "text": cleaned_text,
            "audio_base64": audio_b64,
            "play_chime": play_wake_chime,
            "timestamp": time.time(),
        })

        # Estimate speech duration and transition back to LISTENING
        word_count = len(cleaned_text.split())
        est_duration = max(0.8, word_count * 0.32)

        async def _revert_to_listening():
            try:
                await asyncio.sleep(est_duration)
                if self.state == LifecycleState.SPEAKING and not self.cancellation_token.is_cancelled:
                    await self.set_state(LifecycleState.LISTENING)
            except asyncio.CancelledError:
                pass

        asyncio.create_task(_revert_to_listening())

    def _clean_reply(self, text: str) -> str:
        """
        Strips repetitive canned phrases and boilerplate fluff.
        Keeps replies functional, direct, and minimal.
        Ensures user is addressed as Swastik.
        """
        if not text:
            return ""

        s = text.strip()

        # If it's the exact wake reply, pass it through directly
        if "yes, i am online" in s.lower():
            return "Yes, I am online. What's your command, Swastik?"

        # Replace any stale references to 'king' with 'Swastik'
        s = re.sub(r"\bking\b", "Swastik", s, flags=re.IGNORECASE)

        # Strip repetitive canned openers
        fluff_patterns = [
            r"^wrock online! systems primed and standing by for your command,?\s*(swastik|king\.?)?",
            r"^standing by for your command,?\s*(swastik|king\.?)?",
            r"^greetings,?\s*(swastik|king)!?",
            r"^all systems operational\.?",
            r"^i am operating at peak performance,?\s*(swastik|king)!?",
            r"^i am right here,?\s*(swastik|king)!?",
            r"^i am built to obey your command\.?",
            r"^at your service,?\s*(swastik|king)\.?",
            r"^ready and standing by\.?",
            r"^what is your command\??",
        ]

        for p in fluff_patterns:
            s = re.sub(p, "", s, flags=re.IGNORECASE).strip()

        # Capitalize first letter
        if s:
            s = s[0].upper() + s[1:]
        return s or "Ready."
