"""Re-export ScreenQAEngine from core.intelligence.screen_qa for backend compatibility."""
from core.intelligence.screen_qa import ScreenQAEngine, SYSTEM_PROMPT

__all__ = ["ScreenQAEngine", "SYSTEM_PROMPT"]
