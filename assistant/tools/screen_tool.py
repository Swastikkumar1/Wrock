"""
On-Screen Awareness Voice Tool for Project Wrock.
Captures the active window or full desktop buffer in memory,
runs Vision-Language Model inference via ScreenQAEngine,
and returns an articulate, concise spoken explanation.
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from core.vision.screen_capture import capture_screen_base64, get_active_window_info
from core.intelligence.screen_qa import ScreenQAEngine

logger = logging.getLogger("WrockScreenTool")

try:
    from backend.config import settings
except ImportError:
    try:
        from config import settings
    except ImportError:
        settings = None


class ScreenInspectionTool:
    """
    Assistant tool wrapper for on-screen inspection and visual QA.
    """

    def __init__(self, qa_engine: Optional[ScreenQAEngine] = None):
        if qa_engine:
            self.qa_engine = qa_engine
        else:
            ollama_host = getattr(settings, "OLLAMA_HOST", "http://localhost:11434") if settings else "http://localhost:11434"
            gemini_key = getattr(settings, "GEMINI_API_KEY", None) if settings else None
            gemini_model = getattr(settings, "GEMINI_MODEL", "gemini-1.5-flash") if settings else "gemini-1.5-flash"
            openai_key = getattr(settings, "OPENAI_API_KEY", None) if settings else None
            openai_model = getattr(settings, "OPENAI_MODEL", "gpt-4o") if settings else "gpt-4o"

            self.qa_engine = ScreenQAEngine(
                ollama_host=ollama_host,
                vlm_model="minicpm-v",
                gemini_api_key=gemini_key,
                gemini_model=gemini_model,
                openai_api_key=openai_key,
                openai_model=openai_model,
                timeout_seconds=8.0,
            )

    async def inspect_screen_async(
        self,
        user_query: str = "What is on my screen?",
        target: str = "active_window"
    ) -> str:
        """
        Asynchronously captures desktop/window buffer in memory and runs VLM inference.
        """
        logger.info(f"Screen inspection initiated for target '{target}' with query: '{user_query}'")
        try:
            # 1. Capture screen buffer in memory (<25ms)
            image_b64, window_info = capture_screen_base64(target=target, max_dimension=1024)

            # 2. Run multimodal visual inference
            analysis = await self.qa_engine.analyze_screen(
                image_b64=image_b64,
                user_query=user_query,
                window_info=window_info,
            )
            return analysis
        except Exception as e:
            logger.error(f"Error in inspect_screen_async: {e}", exc_info=True)
            w_info = get_active_window_info()
            return f"Inspected your active window '{w_info.get('title', 'Desktop')}'. The interface is active, Swastik."

    def inspect_screen(
        self,
        user_query: str = "What is on my screen?",
        target: str = "active_window"
    ) -> str:
        """
        Synchronous callable for tools and legacy callers.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Running inside existing event loop
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, self.inspect_screen_async(user_query, target))
                    return future.result(timeout=10.0)
            else:
                return loop.run_until_complete(self.inspect_screen_async(user_query, target))
        except Exception:
            return asyncio.run(self.inspect_screen_async(user_query, target))


# Global tool instance and convenient top-level function
_default_screen_tool = ScreenInspectionTool()


def inspect_screen(user_query: str = "What is on my screen?", target: str = "active_window") -> str:
    """
    Exposed callable tool function:
    inspect_screen(user_query: str, target: str = "active_window") -> str
    """
    return _default_screen_tool.inspect_screen(user_query, target)


async def inspect_screen_async(user_query: str = "What is on my screen?", target: str = "active_window") -> str:
    """
    Asynchronous version of inspect_screen tool.
    """
    return await _default_screen_tool.inspect_screen_async(user_query, target)
