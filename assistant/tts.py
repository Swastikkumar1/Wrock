import base64
import os
import sys
import logging
import httpx
from typing import Optional

_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

try:
    from backend.config import settings
except ImportError:
    from config import settings

logger = logging.getLogger("ElevenLabsTTS")


class ElevenLabsTTSClient:
    """
    Asynchronous ElevenLabs Text-to-Speech client with cancellation support
    and fallback handling.
    """

    def __init__(self, api_key: Optional[str] = None, voice_id: Optional[str] = None):
        self.api_key = api_key or getattr(settings, "ELEVENLABS_API_KEY", None)
        self.voice_id = voice_id or getattr(settings, "ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        self.model_id = getattr(settings, "ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5")

    async def generate_speech_audio(self, text: str, cancellation_token=None) -> Optional[bytes]:
        """
        Generates MP3 audio bytes using ElevenLabs API.
        Returns None if cancelled, offline, or on quota error.
        """
        if not self.api_key or not text.strip():
            return None

        if cancellation_token and cancellation_token.is_cancelled:
            return None

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text.strip(),
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.50,
                "similarity_boost": 0.75,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if cancellation_token and cancellation_token.is_cancelled:
                    return None

                if resp.status_code == 200:
                    return resp.content
                else:
                    logger.warning(f"ElevenLabs API responded with status {resp.status_code}: {resp.text[:120]}")
                    return None
        except Exception as e:
            logger.warning(f"ElevenLabs TTS generation failed: {e}")
            return None

    async def generate_speech_base64(self, text: str, cancellation_token=None) -> Optional[str]:
        audio_bytes = await self.generate_speech_audio(text, cancellation_token)
        if audio_bytes:
            return base64.b64encode(audio_bytes).decode("utf-8")
        return None
