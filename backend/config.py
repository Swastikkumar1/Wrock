import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Project Wrock: Non-Blocking Spatial-AI & OS Automation"
    VERSION: str = "2.0.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # LLM Settings
    LLM_PROVIDER: str = "mock"  # "mock", "openai", "gemini", "ollama"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-pro"
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"

    # Audio & Voice Settings
    WAKE_PHRASE: str = "wake up wrock"
    USER_NAME: str = "Swastik"
    VOICE_IDLE_TIMEOUT_SEC: float = 0.0  # 0.0 disables timeout; stays active once awakened
    SPEECH_CONFIDENCE_THRESHOLD: float = 0.70
    
    # ElevenLabs TTS
    ELEVENLABS_API_KEY: Optional[str] = "f9911bea0ea671a209614af60a0256293b404d7b3069cbe8cd45b83962c65f10"
    ELEVENLABS_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel / Wrock persona
    ELEVENLABS_MODEL_ID: str = "eleven_turbo_v2_5"

    # Spatial Scene & Telemetry Settings
    SCENE_UPDATE_RATE_HZ: int = 30
    DEFAULT_COORDINATE_SYSTEM: str = "WGS84_LOCAL"
    MAX_TRACKED_ENTITIES: int = 64

    # OS-Level Gesture Control & Sensitivity Settings
    ENABLE_OS_GESTURES: bool = True
    CAMERA_INDEX: int = 0
    GESTURE_COOLDOWN_MS: int = 600             # 600ms cooldown for wave/swipes
    SMOOTHING_FACTOR: float = 0.25             # Exponential Moving Average factor (alpha)
    PINCH_THRESHOLD: float = 0.045             # Distance threshold for index-thumb pinch
    MIDDLE_PINCH_THRESHOLD: float = 0.048      # Distance threshold for middle-thumb pinch (right click)
    DRAG_HOLD_DELAY_SEC: float = 0.50          # Hold pinch > 500ms to engage drag
    DEADZONE_PIXELS: float = 4.0               # Minimum pixel delta before moving cursor
    TWO_HAND_ZOOM_THRESHOLD: float = 0.035     # Euclidean delta for two-hand zoom
    SCROLL_SENSITIVITY: int = 35               # Wheel scroll speed per swipe frame
    SWIPE_VELOCITY_THRESHOLD: float = 0.07     # Horizontal velocity for single-hand wave

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
