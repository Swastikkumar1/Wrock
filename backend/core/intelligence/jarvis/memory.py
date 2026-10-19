from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import time

@dataclass
class ConversationTurn:
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

class WrockMemory:
    """
    Rolling conversational and spatial memory for Wrock.
    Maintains dialogue turns, last focused spatial entity, and spatial state history.
    """

    def __init__(self, max_turns: int = 15):
        self.max_turns = max_turns
        self.history: List[ConversationTurn] = []
        self.last_focused_entity_id: Optional[str] = None
        self.last_deployed_anchor: Optional[str] = None
        self.pending_action: Optional[str] = None
        self.pending_data: Dict[str, Any] = {}

    def add_turn(self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        turn = ConversationTurn(role=role, content=content, metadata=metadata or {})
        self.history.append(turn)
        if len(self.history) > self.max_turns:
            self.history.pop(0)

    def set_focus(self, entity_id: str) -> None:
        self.last_focused_entity_id = entity_id

    def get_context_turns(self) -> List[Dict[str, str]]:
        return [{"role": t.role, "content": t.content} for t in self.history]

    def clear(self) -> None:
        self.history.clear()
        self.last_focused_entity_id = None
        self.pending_action = None
        self.pending_data = {}

# Alias for backward compatibility
JarvisMemory = WrockMemory
