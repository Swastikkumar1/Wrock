"""
Multimodal Fusion & Event Broker Layer
Reconciles voice intent, 3D hand tracking, and spatial scene state in sub-100ms cycles.
"""

from .state_synchronizer import MultimodalStateSynchronizer, PerceptionState
from .deictic_resolver import DeicticResolver
from .event_bus import MultimodalEventBus, EventEnvelope

__all__ = [
    "MultimodalStateSynchronizer",
    "PerceptionState",
    "DeicticResolver",
    "MultimodalEventBus",
    "EventEnvelope",
]
