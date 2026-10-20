import asyncio
import time
import os
import sys
import pytest

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from assistant.lifecycle import AssistantLifecycle, CancellationToken, LifecycleState
from os_bridge.input_controller import OSInputController
from vision.gesture_tracker import GestureTracker, HandPoseFrame
from backend.core.intelligence.jarvis import SpatialToolRegistry, WrockMemory, WrockIntentRouter
from backend.core.perception.spatial import SpatialSceneGraph, TacticalObserver, CameraPerspectiveMode


# =====================================================================
# 1. ASSISTANT LIFECYCLE & PERSONA TESTS
# =====================================================================

def test_assistant_lifecycle_strict_wake_word():
    """Verify assistant strictly requires 'Wake up Wrock' when sleeping."""
    async def _run():
        broadcasts = []

        async def mock_broadcast(event_type, payload):
            broadcasts.append((event_type, payload))

        scene = SpatialSceneGraph()
        observer = TacticalObserver(CameraPerspectiveMode.ORBITAL)
        tool_registry = SpatialToolRegistry(scene, observer)
        memory = WrockMemory()
        router = WrockIntentRouter(tool_registry, memory, llm_provider="mock")

        lifecycle = AssistantLifecycle(intent_router=router, broadcast_callback=mock_broadcast)

        assert lifecycle.state == LifecycleState.SLEEPING

        # 1. Ambient speech must be ignored when sleeping
        ignored = await lifecycle.handle_user_transcript("take a screenshot", is_final=True)
        assert ignored is None
        assert lifecycle.state == LifecycleState.SLEEPING

        # 2. Strict wake-phrase awakens the assistant
        wake_res = await lifecycle.handle_user_transcript("wake up wrock", is_final=True)
        assert wake_res is not None
        assert wake_res.get("reply") == "Yes, I am online. What's your command, Swastik?"
        assert lifecycle.state in [LifecycleState.LISTENING, LifecycleState.SPEAKING]

        # 3. Persistent session: subsequent commands execute without wake-phrase
        await lifecycle.set_state(LifecycleState.LISTENING)
        cmd_res = await lifecycle.handle_user_transcript("volume up", is_final=True)
        assert cmd_res is not None
        assert cmd_res.get("action") == "dispatched"

        # Allow async task to complete
        await asyncio.sleep(0.1)

        # 4. Persona check: ensure no 'King' or canned greetings in output
        for b_type, payload in broadcasts:
            if b_type == "ASSISTANT_SPEECH":
                text = payload.get("text", "")
                assert "king" not in text.lower(), f"Fluff found in speech output: {text}"
                assert "how can i help you today" not in text.lower()
                assert "operating at peak performance" not in text.lower()

    asyncio.run(_run())


def test_assistant_instant_barge_in_interruption():
    """Verify barge-in speech aborts active playback immediately."""
    async def _run():
        broadcasts = []

        async def mock_broadcast(event_type, payload):
            broadcasts.append((event_type, payload))

        lifecycle = AssistantLifecycle(broadcast_callback=mock_broadcast)

        # Simulate speaking state
        await lifecycle.set_state(LifecycleState.SPEAKING)
        assert lifecycle.state == LifecycleState.SPEAKING

        # Interrupt with vocal speech 'stop'
        res = await lifecycle.handle_user_transcript("stop", is_final=True)
        assert res is not None
        assert res.get("action") == "interrupted"
        assert lifecycle.cancellation_token.is_cancelled is True
        assert lifecycle.state == LifecycleState.LISTENING

        # Verify broadcast sent to HUD clients
        event_types = [b[0] for b in broadcasts]
        assert "SPEECH_INTERRUPTED" in event_types

    asyncio.run(_run())


def test_assistant_explicit_dismiss():
    """Verify 'dismiss' or 'go to sleep' transitions back to SLEEPING."""
    async def _run():
        lifecycle = AssistantLifecycle()
        await lifecycle.wake_up()
        assert lifecycle.state in [LifecycleState.LISTENING, LifecycleState.SPEAKING]

        # Set to listening to receive command
        await lifecycle.set_state(LifecycleState.LISTENING)
        res = await lifecycle.handle_user_transcript("go to sleep", is_final=True)
        assert res is not None
        assert res.get("action") == "dismissed"
        assert lifecycle.state == LifecycleState.SLEEPING

    asyncio.run(_run())


# =====================================================================
# 2. OS INPUT CONTROLLER & GESTURE CONTROL ENGINE TESTS
# =====================================================================

def test_os_input_controller_cursor_and_smoothing():
    """Verify EMA smoothing and deadzone threshold logic."""
    controller = OSInputController()

    # Move to center
    x1, y1 = controller.move_cursor(0.5, 0.5)
    assert isinstance(x1, int) and isinstance(y1, int)

    # Tiny delta under deadzone (4px) should not jitter
    x2, y2 = controller.move_cursor(0.50005, 0.50005)
    assert abs(x2 - x1) <= 1 and abs(y2 - y1) <= 1

    # Large deliberate delta should move smoothly
    x3, y3 = controller.move_cursor(0.8, 0.8)
    assert x3 > x1
    assert y3 > y1

    controller.shutdown()


def test_os_input_drag_and_drop_state():
    """Verify pinch held > 500ms engages drag-and-drop."""
    controller = OSInputController()
    assert controller.is_dragging is False

    # Immediate pinch (< 500ms) should not engage drag yet
    controller.update_drag_state(is_pinching=True)
    assert controller.is_dragging is False

    # Simulate pinch hold time > 500ms
    controller.pinch_start_time = time.time() - 0.60
    controller.update_drag_state(is_pinching=True)
    assert controller.is_dragging is True

    # Releasing pinch disengages drag
    controller.update_drag_state(is_pinching=False)
    assert controller.is_dragging is False

    controller.shutdown()


def test_gesture_tracker_single_hand_pinches():
    """Verify double-pinch (two pinches in succession) triggers left click, and middle pinch triggers right click."""
    controller = OSInputController()
    tracker = GestureTracker(input_controller=controller)

    # Synthetic hand skeleton (21 points)
    lms = [{"x": 0.5, "y": 0.5, "z": 0.0} for _ in range(21)]
    # Default open fingers
    lms[4] = {"x": 0.40, "y": 0.50, "z": 0.0}   # Thumb tip
    lms[8] = {"x": 0.50, "y": 0.30, "z": 0.0}   # Index tip
    lms[12] = {"x": 0.55, "y": 0.30, "z": 0.0}  # Middle tip

    base_time = 1000.0

    # 1. Normal hover / cursor move
    hand_frame = HandPoseFrame(timestamp=base_time, landmarks=lms, handedness="Right")
    t1 = tracker.process_hands([hand_frame])
    assert t1["gesture"] in ["CURSOR_MOVE", "IDLE"]

    # 2. First index pinch start -> PINCH_START (single pinch should NOT trigger left click yet)
    lms_pinch = [{"x": 0.5, "y": 0.5, "z": 0.0} for _ in range(21)]
    lms_pinch[4] = {"x": 0.50, "y": 0.31, "z": 0.0}   # Close thumb to index tip
    lms_pinch[8] = {"x": 0.50, "y": 0.30, "z": 0.0}
    lms_pinch[12] = {"x": 0.55, "y": 0.30, "z": 0.0}
    t2 = tracker.process_hands([HandPoseFrame(timestamp=base_time + 0.05, landmarks=lms_pinch, handedness="Right")])
    assert t2["gesture"] in ["PINCH_START", "PINCH_HELD"]
    assert t2["gesture"] != "LEFT_CLICK"

    # 3. Release first pinch -> PINCH_RELEASE
    t3 = tracker.process_hands([HandPoseFrame(timestamp=base_time + 0.15, landmarks=lms, handedness="Right")])
    assert t3["gesture"] == "PINCH_RELEASE"

    # 4. Second index pinch within double-pinch window (<0.55s) -> triggers LEFT_CLICK!
    t4 = tracker.process_hands([HandPoseFrame(timestamp=base_time + 0.30, landmarks=lms_pinch, handedness="Right")])
    assert t4["gesture"] == "LEFT_CLICK"

    # 5. Middle pinch (Right Click)
    lms_mid = [{"x": 0.5, "y": 0.5, "z": 0.0} for _ in range(21)]
    lms_mid[8] = {"x": 0.40, "y": 0.30, "z": 0.0}   # Index open
    lms_mid[4] = {"x": 0.55, "y": 0.31, "z": 0.0}   # Close thumb to middle tip
    lms_mid[12] = {"x": 0.55, "y": 0.30, "z": 0.0}
    t5 = tracker.process_hands([HandPoseFrame(timestamp=base_time + 1.0, landmarks=lms_mid, handedness="Right")])
    assert t5["gesture"] == "RIGHT_CLICK"

    controller.shutdown()
    tracker.release()


def test_gesture_tracker_two_hand_zoom_and_swipe():
    """Verify two-hand distance tracking for zoom and two-hand swipe for Alt+Tab."""
    controller = OSInputController()
    tracker = GestureTracker(input_controller=controller)

    # Hand 1 & Hand 2 skeletons
    h1 = [{"x": 0.40, "y": 0.50, "z": 0.0} for _ in range(21)]
    h2 = [{"x": 0.60, "y": 0.50, "z": 0.0} for _ in range(21)]
    h1[8] = {"x": 0.40, "y": 0.40, "z": 0.0}
    h2[8] = {"x": 0.60, "y": 0.40, "z": 0.0}

    frame1 = HandPoseFrame(timestamp=time.time(), landmarks=h1, handedness="Right")
    frame2 = HandPoseFrame(timestamp=time.time(), landmarks=h2, handedness="Left")

    # Seed initial distance
    tracker.process_hands([frame1, frame2])

    # Increase distance -> Zoom In
    h1[8] = {"x": 0.30, "y": 0.40, "z": 0.0}
    h2[8] = {"x": 0.70, "y": 0.40, "z": 0.0}
    t_zoom_in = tracker.process_hands([
        HandPoseFrame(timestamp=time.time() + 0.05, landmarks=h1, handedness="Right"),
        HandPoseFrame(timestamp=time.time() + 0.05, landmarks=h2, handedness="Left"),
    ])
    assert t_zoom_in["gesture"] == "TWO_HAND_ZOOM_IN"

    # Decrease distance -> Zoom Out
    h1[8] = {"x": 0.45, "y": 0.40, "z": 0.0}
    h2[8] = {"x": 0.55, "y": 0.40, "z": 0.0}
    t_zoom_out = tracker.process_hands([
        HandPoseFrame(timestamp=time.time() + 0.10, landmarks=h1, handedness="Right"),
        HandPoseFrame(timestamp=time.time() + 0.10, landmarks=h2, handedness="Left"),
    ])
    assert t_zoom_out["gesture"] == "TWO_HAND_ZOOM_OUT"

    controller.shutdown()
    tracker.release()


# =====================================================================
# 3. FASTAPI REST ENDPOINTS INTEGRATION TEST
# =====================================================================

def test_fastapi_rest_endpoints():
    """Verify health, lifecycle, and gesture endpoints."""
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)

    # 1. Health check
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ONLINE"
    assert "lifecycle_state" in data

    # 2. Lifecycle endpoints
    res_wake = client.post("/api/voice/wake")
    assert res_wake.status_code == 200
    assert res_wake.json()["state"] in ["LISTENING", "SPEAKING"]

    res_interrupt = client.post("/api/voice/interrupt")
    assert res_interrupt.status_code == 200
    assert res_interrupt.json()["status"] == "interrupted"

    res_dismiss = client.post("/api/voice/dismiss")
    assert res_dismiss.status_code == 200
    assert res_dismiss.json()["state"] in ["SLEEPING", "LISTENING"]

    # 3. Gesture settings endpoint
    res_settings = client.get("/api/gestures/settings")
    assert res_settings.status_code == 200
    assert "smoothing_factor" in res_settings.json()
    assert "pinch_threshold" in res_settings.json()
    assert "gesture_cooldown_ms" in res_settings.json()


def test_intent_router_chrome_map_spotify_youtube():
    """Verify routing for Chrome, Map search, Spotify, and YouTube."""
    async def _run():
        scene = SpatialSceneGraph()
        observer = TacticalObserver(CameraPerspectiveMode.ORBITAL)
        tool_registry = SpatialToolRegistry(scene, observer)
        memory = WrockMemory()
        router = WrockIntentRouter(tool_registry, memory, llm_provider="mock")

        # 1. Map Search
        res_map = await router.route_intent("in map search Tokyo", {})
        assert res_map.action_type == "MAP_SEARCH"
        assert "Tokyo" in res_map.spoken_text
        assert res_map.camera_mode == "GODS_EYE"

        # 2. Spotify Search
        res_spotify = await router.route_intent("search daft punk in spotify", {})
        assert res_spotify.action_type == "SPOTIFY_SEARCH"
        assert "daft punk" in res_spotify.spoken_text.lower()

        # 3. YouTube Search
        res_yt = await router.route_intent("search lofi on youtube", {})
        assert res_yt.action_type == "YOUTUBE_SEARCH"
        assert "lofi" in res_yt.spoken_text.lower()

        # 4. Chrome site / search
        res_reddit = await router.route_intent("open reddit on chrome", {})
        assert res_reddit.action_type == "CHROME_OPEN"
        assert "reddit" in res_reddit.spoken_text.lower()

        res_chrome_search = await router.route_intent("go to chrome and search latest quantum computing", {})
        assert res_chrome_search.action_type == "CHROME_OPEN"
        assert "quantum" in res_chrome_search.spoken_text.lower()

        # 5. Direct Google Maps requests (e.g. "just search for the google maps", "open google maps")
        res_maps_conversational = await router.route_intent("just search for the google maps", {})
        assert res_maps_conversational.action_type in ["CHROME_OPEN", "MAP_SEARCH"]
        assert "google maps" in res_maps_conversational.spoken_text.lower()
        assert res_maps_conversational.tool_results[0].arguments.get("query_or_url") == "https://maps.google.com"

        res_open_maps = await router.route_intent("open google maps", {})
        assert res_open_maps.action_type in ["CHROME_OPEN", "MAP_SEARCH"]
        assert "google maps" in res_open_maps.spoken_text.lower()

        # 6. Conversational General Search (strips 'just search for', does not search conversational filler)
        res_clean_search = await router.route_intent("just search for artificial intelligence latest news", {})
        assert res_clean_search.action_type == "CHROME_OPEN"
        assert res_clean_search.tool_results[0].arguments.get("query_or_url") == "artificial intelligence latest news"

    asyncio.run(_run())


def test_antigravity_voice_persona_and_conversations():
    """Verify Antigravity voice persona, dynamic time/date, Hinglish banter, and gesture toggles."""
    async def _run():
        scene = SpatialSceneGraph()
        observer = TacticalObserver(CameraPerspectiveMode.ORBITAL)
        tool_registry = SpatialToolRegistry(scene, observer)
        memory = WrockMemory()
        router = WrockIntentRouter(tool_registry, memory, llm_provider="mock")

        # 1. Creator origin check
        res_creator = await router.route_intent("who made you", {})
        assert "Swastik" in res_creator.spoken_text
        assert res_creator.action_type == "CHAT"

        # 2. Hinglish banter
        res_hinglish = await router.route_intent("han bhai", {})
        assert any(w in res_hinglish.spoken_text.lower() for w in ["swastik", "bhai", "hukum"])

        res_haal = await router.route_intent("kya haal hai", {})
        assert "swastik" in res_haal.spoken_text.lower()

        # 3. Dynamic time and date
        res_time = await router.route_intent("what time is it", {})
        assert "Swastik" in res_time.spoken_text
        assert any(m in res_time.spoken_text.lower() for m in ["am", "pm", ":"])

        res_date = await router.route_intent("what's the date", {})
        assert "Swastik" in res_date.spoken_text
        assert "202" in res_date.spoken_text

        # 4. Science / Tech insights
        res_quantum = await router.route_intent("what is quantum computing", {})
        assert "qubit" in res_quantum.spoken_text.lower() or "superposition" in res_quantum.spoken_text.lower()

        # 5. Jokes and Motivation
        res_joke = await router.route_intent("tell me a joke", {})
        assert len(res_joke.spoken_text) > 10

        res_motivate = await router.route_intent("motivate me", {})
        assert "Swastik" in res_motivate.spoken_text

        # 6. Gesture voice controls
        res_enable_g = await router.route_intent("enable gestures", {})
        assert res_enable_g.action_type == "GESTURE_TOGGLE"
        assert "enabled" in res_enable_g.spoken_text.lower()

        res_disable_g = await router.route_intent("disable gestures", {})
        assert res_disable_g.action_type == "GESTURE_TOGGLE"
        assert "disabled" in res_disable_g.spoken_text.lower()

        # 7. Antigravity Fallback
        res_fallback = await router.route_intent("can you build a spacecraft", {})
        assert "Swastik" in res_fallback.spoken_text
        assert "king" not in res_fallback.spoken_text.lower()

    asyncio.run(_run())


