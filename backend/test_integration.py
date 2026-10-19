import asyncio
import os
import sys

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from backend.core.perception.gestures import LandmarkParser, GestureClassifier, GestureType
from backend.core.perception.spatial import SpatialSceneGraph, EntityTracker, TacticalObserver, CameraPerspectiveMode
from backend.core.intelligence.jarvis import SpatialToolRegistry, WrockMemory, WrockIntentRouter
from backend.core.fusion import MultimodalStateSynchronizer, DeicticResolver

def test_gestures_and_spatial():
    print("[1/4] Testing Gesture Pipeline...")
    parser = LandmarkParser()
    classifier = GestureClassifier()

    # Generate synthetic pinch landmarks
    mock_landmarks = [{"x": 0.5, "y": 0.5, "z": 0.0} for _ in range(21)]
    # Close thumb tip (4) and index tip (8)
    mock_landmarks[4] = {"x": 0.51, "y": 0.49, "z": 0.0}
    mock_landmarks[8] = {"x": 0.50, "y": 0.50, "z": 0.0}

    features = parser.parse(mock_landmarks)
    assert features is not None, "Failed to parse landmarks"
    event = classifier.classify(features)
    print(f" -> Detected Gesture: {event.gesture.value}, pinch_dist={event.pinch_distance:.3f}")

    print("[2/4] Testing Spatial Scene Graph & Kinematics...")
    scene = SpatialSceneGraph()
    tracker = EntityTracker(scene)
    assert len(scene.get_all_entities()) >= 4, "Entities not seeded"
    
    # Tick kinematics
    tracker.update_physics(0.1)
    summary = scene.get_scene_summary()
    print(f" -> Scene Entities: {summary['total_entities']}, Threats: {summary['threats_count']}")

    print("[3/4] Testing Deictic Resolver & Tools...")
    observer = TacticalObserver(CameraPerspectiveMode.ORBITAL)
    tool_registry = SpatialToolRegistry(scene, observer)
    memory = WrockMemory()
    router = WrockIntentRouter(tool_registry, memory, llm_provider="mock")
    sync = MultimodalStateSynchronizer(scene, observer)

    # Hover over drone
    sync.set_hovered_object("DRONE-STARK-01")
    state_snap = sync.get_snapshot().to_dict()

    print("[4/4] Testing Multimodal Intent Routing ('Wrock, inspect this')...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    response = loop.run_until_complete(
        router.route_intent("Wrock, inspect this drone and show diagnostics", state_snap)
    )
    print(f" -> Spoken Response: {response.spoken_text}")
    print(f" -> Tools Called: {[t.tool_name for t in response.tool_results]}")
    assert len(response.tool_results) > 0, "No tools executed"
    assert response.tool_results[0].tool_name == "inspect_entity"
    print("\n[SUCCESS] All Core Wrock Spatial-AI Pipelines Operational!")

if __name__ == "__main__":
    test_gestures_and_spatial()
