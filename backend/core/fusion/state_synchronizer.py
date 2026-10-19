from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
import time
from ..perception.gestures.gesture_classifier import GestureEvent, GestureType
from ..perception.spatial.scene_graph import SpatialSceneGraph
from ..perception.spatial.tactical_observer import TacticalObserver

@dataclass
class PerceptionState:
    timestamp: float = field(default_factory=time.time)
    audio_transcript: str = ""
    is_listening: bool = False
    is_speaking: bool = False
    active_gestures: List[str] = field(default_factory=list)
    cursor_normalized: Dict[str, float] = field(default_factory=lambda: {"x": 0.5, "y": 0.5, "z": 0.0})
    pinch_distance: float = 1.0
    pointing_ray: Dict[str, Any] = field(default_factory=dict)
    hovered_object_id: Optional[str] = None
    selected_object_id: Optional[str] = None
    camera_mode: str = "ORBITAL"
    scene_graph_summary: Dict[str, Any] = field(default_factory=dict)
    user_focus: str = "SCENE"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class MultimodalStateSynchronizer:
    """
    Centralized Multimodal State Synchronizer.
    Fuses continuous sensory streams into a coherent runtime perception state.
    """

    def __init__(self, scene_graph: SpatialSceneGraph, observer: TacticalObserver):
        self.scene_graph = scene_graph
        self.observer = observer
        self.state = PerceptionState()

    def update_gestures(self, gesture_event: GestureEvent) -> None:
        self.state.active_gestures = [gesture_event.gesture.value]
        self.state.cursor_normalized = {
            "x": gesture_event.cursor_screen[0],
            "y": gesture_event.cursor_screen[1],
            "z": gesture_event.cursor_screen[2],
        }
        self.state.pointing_ray = {
            "direction": list(gesture_event.pointing_ray),
        }
        self.state.pinch_distance = gesture_event.pinch_distance
        self.state.timestamp = time.time()

    def update_audio(self, transcript: str, is_listening: bool, is_speaking: bool) -> None:
        self.state.audio_transcript = transcript
        self.state.is_listening = is_listening
        self.state.is_speaking = is_speaking
        self.state.timestamp = time.time()

    def set_hovered_object(self, object_id: Optional[str]) -> None:
        self.state.hovered_object_id = object_id
        self.state.timestamp = time.time()

    def set_selected_object(self, object_id: Optional[str]) -> None:
        self.state.selected_object_id = object_id
        self.state.timestamp = time.time()

    def update_scene_summary(self) -> None:
        self.state.scene_graph_summary = self.scene_graph.get_scene_summary()
        self.state.camera_mode = self.observer.current_mode.value
        self.state.timestamp = time.time()

    def get_snapshot(self) -> PerceptionState:
        self.update_scene_summary()
        return self.state
