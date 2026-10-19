from enum import Enum
from dataclasses import dataclass
from typing import Tuple, Dict, Any

class CameraPerspectiveMode(str, Enum):
    GODS_EYE = "GODS_EYE"          # 90-degree nadir top-down bird's-eye perspective
    ORBITAL = "ORBITAL"            # 45-degree isometric orbital perspective
    TACTICAL_DRONE = "TACTICAL_DRONE"  # Third-person / FPV lock on active drone
    HOLOGRAM = "HOLOGRAM"          # Tabletop holographic workspace perspective

@dataclass
class CameraPose:
    position: Tuple[float, float, float]
    target: Tuple[float, float, float]
    fov: float
    mode: CameraPerspectiveMode

class TacticalObserver:
    """
    Observer perspective controller mirroring the multi-mode camera capabilities
    of Bilawal Sidhu's God's Eye View (Cockpit / Director / Orbital / Top-Down).
    """

    PRESETS = {
        CameraPerspectiveMode.GODS_EYE: CameraPose(
            position=(0.0, 24.0, 0.1),
            target=(0.0, 0.0, 0.0),
            fov=45.0,
            mode=CameraPerspectiveMode.GODS_EYE
        ),
        CameraPerspectiveMode.ORBITAL: CameraPose(
            position=(14.0, 12.0, 14.0),
            target=(0.0, 1.0, 0.0),
            fov=50.0,
            mode=CameraPerspectiveMode.ORBITAL
        ),
        CameraPerspectiveMode.TACTICAL_DRONE: CameraPose(
            position=(-4.5, 4.0, 5.0),
            target=(-4.5, 3.2, 2.0),
            fov=60.0,
            mode=CameraPerspectiveMode.TACTICAL_DRONE
        ),
        CameraPerspectiveMode.HOLOGRAM: CameraPose(
            position=(0.0, 5.0, 9.0),
            target=(0.0, 1.0, 0.0),
            fov=55.0,
            mode=CameraPerspectiveMode.HOLOGRAM
        )
    }

    def __init__(self, initial_mode: CameraPerspectiveMode = CameraPerspectiveMode.ORBITAL):
        self.current_mode = initial_mode
        self.current_pose = self.PRESETS[initial_mode]

    def set_mode(self, mode: CameraPerspectiveMode) -> CameraPose:
        if mode in self.PRESETS:
            self.current_mode = mode
            self.current_pose = self.PRESETS[mode]
        return self.current_pose

    def track_entity(self, entity_pos: Tuple[float, float, float]) -> CameraPose:
        """Positions camera behind and above the tracked entity."""
        ex, ey, ez = entity_pos
        self.current_mode = CameraPerspectiveMode.TACTICAL_DRONE
        self.current_pose = CameraPose(
            position=(ex - 2.0, ey + 1.8, ez + 3.0),
            target=(ex, ey, ez),
            fov=60.0,
            mode=CameraPerspectiveMode.TACTICAL_DRONE
        )
        return self.current_pose

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.current_mode.value,
            "position": list(self.current_pose.position),
            "target": list(self.current_pose.target),
            "fov": self.current_pose.fov,
        }
