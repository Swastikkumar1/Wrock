import asyncio
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Set, Dict, Any, Optional
from fastapi import WebSocket

@dataclass
class EventEnvelope:
    event_type: str  # "SCENE_UPDATE", "PERCEPTION_STATE", "GESTURE_EVENT", "VOICE_INTENT", "TOOL_EXECUTION", "SYSTEM_ALERT"
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps({
            "event_type": self.event_type,
            "payload": self.payload,
            "timestamp": self.timestamp,
        })

class MultimodalEventBus:
    """
    High-throughput asynchronous broadcast bus (<100ms transport)
    connecting perception engines, cognitive router, and 3D spatial client.
    """

    def __init__(self):
        self._active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._active_connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self._active_connections:
                self._active_connections.remove(websocket)

    async def broadcast(self, event_type: str, payload: Dict[str, Any]) -> None:
        envelope = EventEnvelope(event_type=event_type, payload=payload)
        message_json = envelope.to_json()

        async with self._lock:
            stale_connections = []
            for ws in self._active_connections:
                try:
                    await ws.send_text(message_json)
                except Exception:
                    stale_connections.append(ws)

            for ws in stale_connections:
                self._active_connections.discard(ws)

    def client_count(self) -> int:
        return len(self._active_connections)
