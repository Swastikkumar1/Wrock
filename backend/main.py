import asyncio
import os
import sys
import time
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List

# Ensure repository root is at the head of sys.path so 'backend', 'assistant', 'vision', 'os_bridge' are resolvable
_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
elif sys.path[0] != _parent_dir:
    sys.path.remove(_parent_dir)
    sys.path.insert(0, _parent_dir)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from backend.config import settings
    from backend.core.perception.gestures import LandmarkParser, GestureClassifier, SpatialRaycaster, GestureType
    from backend.core.perception.spatial import SpatialSceneGraph, EntityTracker, TacticalObserver, CameraPerspectiveMode
    from backend.core.intelligence.jarvis import VoiceEngine, SpatialToolRegistry, WrockMemory, WrockIntentRouter
    from backend.core.fusion import MultimodalStateSynchronizer, DeicticResolver, MultimodalEventBus, EventEnvelope
except (ImportError, ValueError):
    from config import settings
    from core.perception.gestures import LandmarkParser, GestureClassifier, SpatialRaycaster, GestureType
    from core.perception.spatial import SpatialSceneGraph, EntityTracker, TacticalObserver, CameraPerspectiveMode
    from core.intelligence.jarvis import VoiceEngine, SpatialToolRegistry, WrockMemory, WrockIntentRouter
    from core.fusion import MultimodalStateSynchronizer, DeicticResolver, MultimodalEventBus, EventEnvelope

from assistant.lifecycle import AssistantLifecycle, LifecycleState
from assistant.tts import ElevenLabsTTSClient
from os_bridge.input_controller import OSInputController
from vision.gesture_tracker import GestureTracker, HandPoseFrame

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("WrockEyeServer")

# Instantiate Core Pillars
scene_graph = SpatialSceneGraph()
entity_tracker = EntityTracker(scene_graph)
observer = TacticalObserver(CameraPerspectiveMode.ORBITAL)

landmark_parser = LandmarkParser()
gesture_classifier = GestureClassifier()
raycaster = SpatialRaycaster()

voice_engine = VoiceEngine(wake_word=getattr(settings, "WAKE_PHRASE", "wake up wrock"))
memory = WrockMemory()
tool_registry = SpatialToolRegistry(scene_graph, observer)
intent_router = WrockIntentRouter(
    tool_registry=tool_registry,
    memory=memory,
    llm_provider=settings.LLM_PROVIDER,
    openai_api_key=settings.OPENAI_API_KEY,
    openai_model=settings.OPENAI_MODEL,
    gemini_api_key=settings.GEMINI_API_KEY,
    ollama_host=settings.OLLAMA_HOST,
    ollama_model=settings.OLLAMA_MODEL,
)

synchronizer = MultimodalStateSynchronizer(scene_graph, observer)
deictic_resolver = DeicticResolver(scene_graph)
event_bus = MultimodalEventBus()

# Instantiate Refactored OS-Level Input Controller & Vision Gesture Tracker
os_input_controller = OSInputController()
gesture_tracker = GestureTracker(input_controller=os_input_controller)

# Hook up gesture telemetry broadcasting
def _on_gesture_telemetry(gesture_name: str, payload: Dict[str, Any]):
    asyncio.create_task(event_bus.broadcast("OS_GESTURE_EVENT", {
        "gesture": gesture_name,
        "payload": payload,
        "timestamp": time.time(),
    }))

gesture_tracker.on_gesture_telemetry = _on_gesture_telemetry

# Instantiate Non-Blocking Conversational Lifecycle Manager
elevenlabs_tts = ElevenLabsTTSClient(
    api_key=settings.ELEVENLABS_API_KEY,
    voice_id=settings.ELEVENLABS_VOICE_ID,
)

assistant_lifecycle = AssistantLifecycle(
    intent_router=intent_router,
    tts_client=elevenlabs_tts,
    broadcast_callback=event_bus.broadcast,
)

# Background High-Throughput Kinematics Loop
async def telemetry_event_loop():
    logger.info("Initializing 30Hz Spatial Telemetry & Kinematics Loop...")
    last_time = time.time()
    while True:
        try:
            now = time.time()
            dt = now - last_time
            last_time = now

            # Advance kinematics for satellites, drones, and rovers
            entity_tracker.update_physics(dt)
            synchronizer.update_scene_summary()

            # Broadcast scene state to connected spatial clients
            if event_bus.client_count() > 0:
                scene_data = scene_graph.serialize_full_scene()
                scene_data["observer"] = observer.to_dict()
                await event_bus.broadcast("SCENE_UPDATE", scene_data)

            await asyncio.sleep(1.0 / settings.SCENE_UPDATE_RATE_HZ)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in telemetry loop: {e}", exc_info=True)
            await asyncio.sleep(0.1)

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop_task = asyncio.create_task(telemetry_event_loop())
    logger.info(f"Project Wrock-Eye Backend started on http://{settings.HOST}:{settings.PORT}")
    yield
    loop_task.cancel()
    await asyncio.gather(loop_task, return_exceptions=True)
    os_input_controller.shutdown()
    gesture_tracker.release()
    logger.info("Project Wrock-Eye Backend cleanly shutdown.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Schemas
class VoiceCommandRequest(BaseModel):
    command: str
    is_final: bool = True
    hovered_entity_id: Optional[str] = None

class GestureSettingsUpdate(BaseModel):
    smoothing_factor: Optional[float] = None
    pinch_threshold: Optional[float] = None
    gesture_cooldown_ms: Optional[int] = None
    enable_os_gestures: Optional[bool] = None

# REST Endpoints
@app.get("/health")
def health_check():
    return {
        "status": "ONLINE",
        "system": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "clients_connected": event_bus.client_count(),
        "entities_tracked": len(scene_graph.get_all_entities()),
        "observer_mode": observer.current_mode.value,
        "llm_provider": settings.LLM_PROVIDER,
        "lifecycle_state": assistant_lifecycle.state.value,
        "os_gestures_enabled": getattr(settings, "ENABLE_OS_GESTURES", True),
    }

@app.get("/api/scene")
def get_scene():
    data = scene_graph.serialize_full_scene()
    data["observer"] = observer.to_dict()
    return data

@app.get("/api/tools")
def get_tools():
    return tool_registry.get_tool_definitions()

@app.get("/api/lifecycle")
def get_lifecycle_status():
    return {
        "state": assistant_lifecycle.state.value,
        "is_awake": assistant_lifecycle.state != LifecycleState.SLEEPING,
        "last_activity": assistant_lifecycle.last_user_activity,
    }

@app.post("/api/voice/interrupt")
async def interrupt_speech_endpoint():
    """Immediately aborts speech playback (Barge-In)."""
    await assistant_lifecycle.interrupt_speech(reason="rest_api_trigger")
    return {"status": "interrupted", "state": assistant_lifecycle.state.value}

@app.post("/api/voice/wake")
async def wake_up_endpoint():
    """Explicitly wakes up Wrock without fluff."""
    await assistant_lifecycle.wake_up()
    return {"status": "awake", "state": assistant_lifecycle.state.value}

@app.post("/api/voice/dismiss")
async def dismiss_endpoint():
    """Dismisses Wrock into SLEEPING state."""
    await assistant_lifecycle.dismiss()
    return {"status": "dismissed", "state": assistant_lifecycle.state.value}

@app.post("/api/voice/command")
async def execute_voice_command(req: VoiceCommandRequest):
    if req.hovered_entity_id:
        synchronizer.set_hovered_object(req.hovered_entity_id)

    snapshot = synchronizer.get_snapshot().to_dict()
    res = await assistant_lifecycle.handle_user_transcript(req.command, req.is_final, snapshot)
    return res or {"status": "processed"}

@app.get("/api/gestures/settings")
def get_gesture_settings():
    return {
        "smoothing_factor": getattr(settings, "SMOOTHING_FACTOR", 0.25),
        "pinch_threshold": getattr(settings, "PINCH_THRESHOLD", 0.045),
        "gesture_cooldown_ms": getattr(settings, "GESTURE_COOLDOWN_MS", 600),
        "enable_os_gestures": getattr(settings, "ENABLE_OS_GESTURES", True),
        "camera_running": gesture_tracker.is_running,
    }

@app.post("/api/gestures/settings")
def update_gesture_settings(req: GestureSettingsUpdate):
    if req.smoothing_factor is not None:
        settings.SMOOTHING_FACTOR = req.smoothing_factor
    if req.pinch_threshold is not None:
        settings.PINCH_THRESHOLD = req.pinch_threshold
    if req.gesture_cooldown_ms is not None:
        settings.GESTURE_COOLDOWN_MS = req.gesture_cooldown_ms
    if req.enable_os_gestures is not None:
        settings.ENABLE_OS_GESTURES = req.enable_os_gestures
    return {"status": "updated", "settings": get_gesture_settings()}

@app.post("/api/gestures/camera/start")
def start_camera_endpoint(camera_index: Optional[int] = None):
    success = gesture_tracker.start_background_camera(camera_index)
    return {"status": "started" if success else "failed", "running": gesture_tracker.is_running}

@app.post("/api/gestures/camera/stop")
def stop_camera_endpoint():
    gesture_tracker.stop_background_camera()
    return {"status": "stopped", "running": False}

# High-Throughput Bidirectional WebSocket Pipeline
@app.websocket("/ws/spatial")
async def spatial_websocket(websocket: WebSocket):
    await event_bus.connect(websocket)
    logger.info("New Spatial HUD Client connected to /ws/spatial.")
    try:
        # Send initial full scene sync
        initial_scene = scene_graph.serialize_full_scene()
        initial_scene["observer"] = observer.to_dict()
        await websocket.send_text(EventEnvelope("SCENE_UPDATE", initial_scene).to_json())

        # Send initial lifecycle status
        await websocket.send_text(EventEnvelope("LIFECYCLE_STATE", {
            "state": assistant_lifecycle.state.value,
            "is_awake": assistant_lifecycle.state != LifecycleState.SLEEPING,
        }).to_json())

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            payload = data.get("payload", {})

            # 1. Hand Landmarks Stream (from client-side MediaPipe or camera feed)
            if msg_type == "HAND_LANDMARKS":
                raw_landmarks = payload.get("multi_hand_landmarks") or payload.get("landmarks", [])
                handedness = payload.get("handedness", "Right")

                # If OS-level gesture control is enabled, process through full GestureTracker
                if getattr(settings, "ENABLE_OS_GESTURES", True) and raw_landmarks:
                    now = time.time()
                    hands_poses: List[HandPoseFrame] = []

                    if isinstance(raw_landmarks, list) and len(raw_landmarks) > 0 and isinstance(raw_landmarks[0], list):
                        # List of multiple hands
                        for idx, h_lms in enumerate(raw_landmarks):
                            h_label = handedness[idx] if isinstance(handedness, list) and idx < len(handedness) else ("Left" if idx == 1 else "Right")
                            hands_poses.append(HandPoseFrame(timestamp=now, landmarks=h_lms, handedness=h_label))
                    elif isinstance(raw_landmarks, list) and len(raw_landmarks) > 0 and isinstance(raw_landmarks[0], dict):
                        hands_poses.append(HandPoseFrame(timestamp=now, landmarks=raw_landmarks, handedness=str(handedness)))

                    if hands_poses:
                        # Process gestures directly into OS inputs
                        gesture_tracker.process_hands(hands_poses)

                # Also update 3D spatial scene synchronizer for God's Eye map
                primary_lms = raw_landmarks[0] if (isinstance(raw_landmarks, list) and len(raw_landmarks) > 0 and isinstance(raw_landmarks[0], list)) else raw_landmarks
                if primary_lms and isinstance(primary_lms, list) and len(primary_lms) > 0 and isinstance(primary_lms[0], dict):
                    features = landmark_parser.parse(primary_lms)
                    gesture_event = gesture_classifier.classify(features)
                    synchronizer.update_gestures(gesture_event)

                    current_hovered = synchronizer.state.hovered_object_id
                    action = deictic_resolver.evaluate_gesture_action(gesture_event, current_hovered)
                    if action:
                        if action["action"] == "LOCK_TARGET" and current_hovered:
                            scene_graph.lock_entity(current_hovered, True)
                        elif action["action"] == "CYCLE_PERSPECTIVE_NEXT":
                            modes = list(CameraPerspectiveMode)
                            idx = modes.index(observer.current_mode)
                            next_mode = modes[(idx + 1) % len(modes)]
                            observer.set_mode(next_mode)

                    await event_bus.broadcast("GESTURE_EVENT", {
                        "gesture": gesture_event.gesture.value,
                        "confidence": gesture_event.confidence,
                        "cursor": {
                            "x": gesture_event.cursor_screen[0],
                            "y": gesture_event.cursor_screen[1],
                            "z": gesture_event.cursor_screen[2],
                        },
                        "pointing_ray": list(gesture_event.pointing_ray),
                        "pinch_distance": gesture_event.pinch_distance,
                        "action_triggered": action,
                    })

            # 2. Hover / Raycast Ray update from client viewport
            elif msg_type == "HOVER_UPDATE":
                entity_id = payload.get("entity_id")
                synchronizer.set_hovered_object(entity_id)

            # 3. Voice Stream Transcript (Decoupled & Non-blocking)
            elif msg_type == "VOICE_TRANSCRIPT":
                text = payload.get("text", "").strip()
                is_final = payload.get("is_final", False)

                synchronizer.update_audio(text, is_listening=True, is_speaking=assistant_lifecycle.state == LifecycleState.SPEAKING)
                snapshot = synchronizer.get_snapshot().to_dict()

                # Process through AssistantLifecycle (handles strict wake-up, barge-in, persistent session)
                await assistant_lifecycle.handle_user_transcript(text, is_final, snapshot)

            # 4. Instant Speech Interrupt from client (Barge-In)
            elif msg_type == "SPEECH_INTERRUPT":
                reason = payload.get("reason", "client_trigger")
                await assistant_lifecycle.interrupt_speech(reason)

            # 5. Direct Wake & Dismiss from UI
            elif msg_type == "WAKE":
                await assistant_lifecycle.wake_up()

            elif msg_type == "DISMISS":
                await assistant_lifecycle.dismiss()

            # 6. Direct Command (from UI buttons or text input)
            elif msg_type == "COMMAND":
                cmd_text = payload.get("text", "").strip()
                if cmd_text:
                    if assistant_lifecycle.state == LifecycleState.SLEEPING:
                        # Explicit manual command wakes assistant
                        await assistant_lifecycle.wake_up()
                    snapshot = synchronizer.get_snapshot().to_dict()
                    await assistant_lifecycle.execute_command(cmd_text, snapshot)

            # 6. Direct POV Stream Toggle
            elif msg_type == "SET_POV":
                target_id = payload.get("target_id", "DRONE-STARK-01")
                res = tool_registry.execute_tool("watch_entity_pov", {"target_id": target_id})
                await event_bus.broadcast("VOICE_INTENT", {
                    "spoken_text": res.output_message,
                    "hud_alert": res.output_message,
                    "target_entity_id": target_id,
                    "camera_mode": "GODS_EYE",
                    "pov_entity_id": target_id,
                    "action_type": "POV_ENGAGED",
                    "tools_called": ["watch_entity_pov"],
                })

            # 7. Optical Hand Pinch-Zoom on Map
            elif msg_type == "MAP_PINCH_ZOOM":
                factor = payload.get("zoom_factor", 1.0)
                res = tool_registry.execute_tool("zoom_gods_eye_map", {"zoom_factor": factor})
                await event_bus.broadcast("MAP_UPDATE", res.telemetry_payload)

            # 8. Camera Switch Direct Action
            elif msg_type == "SET_CAMERA_MODE":
                mode_str = payload.get("mode", "GODS_EYE")
                try:
                    mode = CameraPerspectiveMode(mode_str)
                    observer.set_mode(mode)
                    await event_bus.broadcast("CAMERA_UPDATE", observer.to_dict())
                except ValueError:
                    pass

    except WebSocketDisconnect:
        await event_bus.disconnect(websocket)
        logger.info("Spatial HUD Client disconnected from /ws/spatial.")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        await event_bus.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=True)
