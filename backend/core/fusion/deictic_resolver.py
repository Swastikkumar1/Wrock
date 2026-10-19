from typing import Optional, Dict, Any, Tuple
import re
from ..perception.gestures.gesture_classifier import GestureType, GestureEvent
from .state_synchronizer import PerceptionState
from ..perception.spatial.scene_graph import SpatialSceneGraph

class DeicticResolver:
    """
    Deictic & Multimodal Gesture Resolver.
    Binds ambiguous verbal references ("this", "that drone", "here")
    to concrete 3D spatial entities based on hand pointing and cursor hover.
    """

    DEICTIC_PATTERNS = [
        re.compile(r"\b(this|this one|this target|this drone|this object)\b", re.IGNORECASE),
        re.compile(r"\b(that|that one|that target|that drone|that bogey)\b", re.IGNORECASE),
        re.compile(r"\b(here|right here|over here)\b", re.IGNORECASE),
        re.compile(r"\b(it|its|target)\b", re.IGNORECASE),
    ]

    def __init__(self, scene_graph: SpatialSceneGraph):
        self.scene_graph = scene_graph

    def has_deictic_reference(self, utterance: str) -> bool:
        return any(pat.search(utterance) is not None for pat in self.DEICTIC_PATTERNS)

    def resolve_target(self, utterance: str, perception_state: PerceptionState) -> Optional[str]:
        """
        Returns resolved entity ID if the utterance contains deictic pointers,
        or None if no deictic reference or hovered object exists.
        """
        if not self.has_deictic_reference(utterance):
            return None

        # Priority 1: Entity actively hovered via hand pointing ray or cursor reticle
        if perception_state.hovered_object_id:
            return perception_state.hovered_object_id

        # Priority 2: Entity currently locked
        if perception_state.selected_object_id:
            return perception_state.selected_object_id

        # Priority 3: Nearest entity to center of screen (0.5, 0.5)
        entities = self.scene_graph.get_all_entities()
        if entities:
            # Pick first active drone or satellite
            for e in entities:
                if e.is_locked:
                    return e.id
            return entities[0].id

        return None

    def evaluate_gesture_action(self, gesture_event: GestureEvent, hovered_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Translates physical gestures into immediate spatial UI actions.
        """
        if gesture_event.gesture == GestureType.PINCH_START and hovered_id:
            return {
                "action": "LOCK_TARGET",
                "target_id": hovered_id,
                "reason": "Direct pinch on entity"
            }
        elif gesture_event.gesture == GestureType.SWIPE_LEFT:
            return {
                "action": "CYCLE_PERSPECTIVE_NEXT",
                "reason": "Horizontal swipe left"
            }
        elif gesture_event.gesture == GestureType.SWIPE_RIGHT:
            return {
                "action": "CYCLE_PERSPECTIVE_PREV",
                "reason": "Horizontal swipe right"
            }
        elif gesture_event.gesture == GestureType.OPEN_PALM and not hovered_id:
            return {
                "action": "RESET_VIEWPORT",
                "reason": "Open palm gesture in empty space"
            }
        return None
