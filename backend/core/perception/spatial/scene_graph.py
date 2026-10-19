from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
import math
import time

class EntityType(str, Enum):
    DRONE = "DRONE"
    SATELLITE = "SATELLITE"
    VEHICLE = "VEHICLE"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    POI = "POI"
    PERSONNEL = "PERSONNEL"

class ThreatLevel(str, Enum):
    FRIENDLY = "FRIENDLY"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"
    HOSTILE = "HOSTILE"

@dataclass
class SpatialPosition:
    x: float
    y: float
    z: float

@dataclass
class SpatialVelocity:
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0

@dataclass
class SpatialEntity:
    id: str
    name: str
    type: EntityType
    position: SpatialPosition
    velocity: SpatialVelocity = field(default_factory=SpatialVelocity)
    heading_deg: float = 0.0
    altitude_m: float = 0.0
    threat_level: ThreatLevel = ThreatLevel.NEUTRAL
    is_locked: bool = False
    is_inspected: bool = False
    bounding_radius: float = 1.5
    spatial_anchor_id: Optional[str] = None
    telemetry: Dict[str, Any] = field(default_factory=dict)
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["type"] = self.type.value
        data["threat_level"] = self.threat_level.value
        return data

class SpatialSceneGraph:
    """
    Dynamic 3D Spatial Scene Graph inspired by Bilawal Sidhu's God's Eye View.
    Maintains hierarchical spatial entities, spatial anchors, and spatial queries.
    """

    def __init__(self, origin_lat_lon: Tuple[float, float] = (37.7749, -122.4194)):
        self.origin_lat_lon = origin_lat_lon
        self._entities: Dict[str, SpatialEntity] = {}
        self._spatial_anchors: Dict[str, Dict[str, Any]] = {}
        self._last_mutation_time: float = time.time()

    def upsert_entity(self, entity: SpatialEntity) -> None:
        entity.last_updated = time.time()
        self._entities[entity.id] = entity
        self._last_mutation_time = time.time()

    def get_entity(self, entity_id: str) -> Optional[SpatialEntity]:
        return self._entities.get(entity_id)

    def remove_entity(self, entity_id: str) -> bool:
        if entity_id in self._entities:
            del self._entities[entity_id]
            self._last_mutation_time = time.time()
            return True
        return False

    def get_all_entities(self) -> List[SpatialEntity]:
        return list(self._entities.values())

    def lock_entity(self, entity_id: str, lock: bool = True) -> bool:
        if entity_id in self._entities:
            self._entities[entity_id].is_locked = lock
            self._last_mutation_time = time.time()
            return True
        return False

    def inspect_entity(self, entity_id: str, inspect: bool = True) -> bool:
        if entity_id in self._entities:
            self._entities[entity_id].is_inspected = inspect
            self._last_mutation_time = time.time()
            return True
        return False

    def query_radius(self, center: Tuple[float, float, float], radius: float) -> List[SpatialEntity]:
        cx, cy, cz = center
        results = []
        for e in self._entities.values():
            dx = e.position.x - cx
            dy = e.position.y - cy
            dz = e.position.z - cz
            dist = math.sqrt(dx*dx + dy*dy + dz*dz)
            if dist <= radius:
                results.append(e)
        return results

    def add_spatial_anchor(self, anchor_id: str, label: str, position: Tuple[float, float, float]) -> Dict[str, Any]:
        anchor = {
            "id": anchor_id,
            "label": label,
            "x": position[0],
            "y": position[1],
            "z": position[2],
            "created_at": time.time()
        }
        self._spatial_anchors[anchor_id] = anchor
        self._last_mutation_time = time.time()
        return anchor

    def get_anchors(self) -> List[Dict[str, Any]]:
        return list(self._spatial_anchors.values())

    def get_scene_summary(self) -> Dict[str, Any]:
        entities = list(self._entities.values())
        return {
            "total_entities": len(entities),
            "threats_count": sum(1 for e in entities if e.threat_level == ThreatLevel.HOSTILE),
            "locked_entity_id": next((e.id for e in entities if e.is_locked), None),
            "entity_ids": [e.id for e in entities],
            "anchors_count": len(self._spatial_anchors),
            "last_mutation": self._last_mutation_time,
        }

    def serialize_full_scene(self) -> Dict[str, Any]:
        return {
            "origin_lat_lon": self.origin_lat_lon,
            "entities": [e.to_dict() for e in self._entities.values()],
            "anchors": list(self._spatial_anchors.values()),
            "summary": self.get_scene_summary(),
        }
