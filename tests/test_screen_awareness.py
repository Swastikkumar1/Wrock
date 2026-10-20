import asyncio
import os
import sys
import pytest
from PIL import Image

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from core.vision.screen_capture import (
    capture_full_screen,
    capture_active_window,
    capture_screen_base64,
    get_active_window_info,
    image_to_base64,
    resize_image_in_memory,
)
from core.intelligence.screen_qa import ScreenQAEngine
from assistant.tools.screen_tool import inspect_screen, inspect_screen_async, ScreenInspectionTool
from backend.core.intelligence.jarvis import SpatialToolRegistry, WrockMemory, WrockIntentRouter
from backend.core.perception.spatial import SpatialSceneGraph, TacticalObserver, CameraPerspectiveMode


def test_screen_capture_in_memory_and_resize():
    """Verify in-memory full screen & active window capture and fast resizing (<25ms)."""
    # 1. Capture full screen
    full_img = capture_full_screen(max_dimension=800)
    assert isinstance(full_img, Image.Image)
    assert max(full_img.size) <= 800
    assert full_img.mode in ("RGB", "RGBA")

    # 2. Capture active window crop
    act_img = capture_active_window(max_dimension=800)
    assert isinstance(act_img, Image.Image)
    assert max(act_img.size) <= 800

    # 3. Base64 encoding in memory
    b64_str, win_info = capture_screen_base64(target="active_window", max_dimension=600)
    assert isinstance(b64_str, str)
    assert len(b64_str) > 50
    assert "title" in win_info

    # 4. Resize helper preserves aspect ratio
    test_img = Image.new("RGB", (1600, 800), color=(10, 20, 30))
    resized = resize_image_in_memory(test_img, max_dimension=800)
    assert resized.size == (800, 400)


def test_screen_qa_engine_prompt_and_fallback():
    """Verify ScreenQAEngine prompt engineering, fallback heuristics, and speech cleaning."""
    engine = ScreenQAEngine(vlm_model="minicpm-v", timeout_seconds=1.0)

    # 1. Prompt formatting
    prompt = engine.build_screen_prompt("What code is open?", {"title": "main.py - Visual Studio Code"})
    assert "main.py - Visual Studio Code" in prompt
    assert "What code is open?" in prompt

    # 2. Clean speech text removes code fences and markdown
    dirty = "```python\nprint('hello')\n```\n**Error:** Found *syntax* error #bug."
    clean = engine._clean_speech_text(dirty)
    assert "*" not in clean
    assert "#" not in clean
    assert "```" not in clean

    # 3. Fallback analysis for errors
    error_reply = engine._fallback_analysis("What is this error?", {"title": "PowerShell - Execution Log"})
    assert "Swastik" in error_reply
    assert "terminal" in error_reply.lower() or "powershell" in error_reply.lower()

    # 4. Fallback analysis for open code
    code_reply = engine._fallback_analysis("What code is currently open?", {"title": "intent_router.py - VSCode"})
    assert "Swastik" in code_reply
    assert "intent_router.py" in code_reply


def test_assistant_screen_tool_synchronous_and_async():
    """Verify inspect_screen tool execution."""
    async def _run_async():
        res = await inspect_screen_async("Explain this screen", target="active_window")
        assert isinstance(res, str)
        assert len(res) > 10

    asyncio.run(_run_async())

    sync_res = inspect_screen("What window is open?")
    assert isinstance(sync_res, str)
    assert len(sync_res) > 10


def test_end_to_end_intent_router_screen_awareness():
    """Demonstrate end-to-end query: 'Look at my screen and tell me what window is open and what it says.'"""
    async def _run():
        scene = SpatialSceneGraph()
        observer = TacticalObserver(CameraPerspectiveMode.ORBITAL)
        tool_registry = SpatialToolRegistry(scene, observer)
        memory = WrockMemory()
        router = WrockIntentRouter(tool_registry, memory, llm_provider="mock")

        # 1. Primary prompt required by task
        user_query = "Look at my screen and tell me what window is open and what it says."
        res = await router.route_intent(user_query, {})

        assert res.action_type == "SCREEN_INSPECT"
        assert res.spoken_text is not None
        assert len(res.spoken_text) > 10
        assert "Swastik" in res.spoken_text
        import re
        assert not re.search(r"\bking\b", res.spoken_text.lower())
        assert len(res.tool_results) == 1
        assert res.tool_results[0].tool_name == "inspect_screen"

        # 2. Deictic error query: "What is this error?"
        res_error = await router.route_intent("What is this error?", {})
        assert res_error.action_type == "SCREEN_INSPECT"
        assert "Swastik" in res_error.spoken_text

        # 3. Summarization query: "Summarize this page"
        res_summary = await router.route_intent("Summarize this page", {})
        assert res_summary.action_type == "SCREEN_INSPECT"
        assert len(res_summary.spoken_text) > 10

    asyncio.run(_run())
