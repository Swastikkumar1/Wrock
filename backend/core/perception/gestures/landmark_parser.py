from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import math
import numpy as np

# Canonical 21 MediaPipe Hand Landmarks
LANDMARK_NAMES = [
    "WRIST",
    "THUMB_CMC", "THUMB_MCP", "THUMB_IP", "THUMB_TIP",
    "INDEX_FINGER_MCP", "INDEX_FINGER_PIP", "INDEX_FINGER_DIP", "INDEX_FINGER_TIP",
    "MIDDLE_FINGER_MCP", "MIDDLE_FINGER_PIP", "MIDDLE_FINGER_DIP", "MIDDLE_FINGER_TIP",
    "RING_FINGER_MCP", "RING_FINGER_PIP", "RING_FINGER_DIP", "RING_FINGER_TIP",
    "PINKY_MCP", "PINKY_PIP", "PINKY_DIP", "PINKY_TIP"
]

@dataclass
class HandLandmark:
    id: int
    name: str
    x: float
    y: float
    z: float

@dataclass
class HandPoseFeatures:
    palm_center: np.ndarray
    palm_scale: float
    palm_normal: np.ndarray
    is_thumb_open: bool
    is_index_open: bool
    is_middle_open: bool
    is_ring_open: bool
    is_pinky_open: bool
    pinch_distance: float
    pointing_vector: np.ndarray
    wrist_roll_rad: float

class LandmarkParser:
    """
    Parses canonical 21-point MediaPipe hand landmark arrays into normalized
    geometric spatial vectors and finger state booleans.
    """

    def __init__(self, smoothing_factor: float = 0.4):
        self.smoothing_factor = smoothing_factor
        self._prev_landmarks: Optional[np.ndarray] = None

    def parse(self, raw_landmarks: List[Dict[str, Any]]) -> Optional[HandPoseFeatures]:
        if not raw_landmarks or len(raw_landmarks) < 21:
            return None

        # Convert to Nx3 numpy array
        coords = np.array([[lm.get("x", 0.0), lm.get("y", 0.0), lm.get("z", 0.0)] for lm in raw_landmarks[:21]], dtype=np.float32)

        # Apply exponential moving average smoothing
        if self._prev_landmarks is not None:
            coords = self.smoothing_factor * coords + (1.0 - self.smoothing_factor) * self._prev_landmarks
        self._prev_landmarks = coords

        wrist = coords[0]
        thumb_tip = coords[4]
        index_mcp = coords[5]
        index_tip = coords[8]
        middle_mcp = coords[9]
        middle_tip = coords[12]
        ring_mcp = coords[13]
        ring_tip = coords[16]
        pinky_mcp = coords[17]
        pinky_tip = coords[20]

        # Palm center: average of wrist, index_mcp, and pinky_mcp
        palm_center = (wrist + index_mcp + pinky_mcp) / 3.0

        # Palm scale: distance between wrist and middle_mcp (scale-invariant reference)
        palm_scale = float(np.linalg.norm(middle_mcp - wrist))
        if palm_scale < 1e-5:
            palm_scale = 1.0

        # Palm normal vector (cross product of index_mcp-wrist and pinky_mcp-wrist)
        v1 = index_mcp - wrist
        v2 = pinky_mcp - wrist
        cross_norm = np.cross(v1, v2)
        norm_mag = np.linalg.norm(cross_norm)
        palm_normal = cross_norm / norm_mag if norm_mag > 1e-5 else np.array([0.0, 0.0, 1.0])

        # Finger extension states based on tip distance from wrist vs MCP distance from wrist
        def is_finger_extended(tip_idx: int, pip_idx: int, mcp_idx: int) -> bool:
            tip_dist = np.linalg.norm(coords[tip_idx] - wrist)
            pip_dist = np.linalg.norm(coords[pip_idx] - wrist)
            return bool(tip_dist > pip_dist * 1.15)

        is_thumb_open = float(np.linalg.norm(thumb_tip - index_mcp)) > (palm_scale * 0.5)
        is_index_open = is_finger_extended(8, 6, 5)
        is_middle_open = is_finger_extended(12, 10, 9)
        is_ring_open = is_finger_extended(16, 14, 13)
        is_pinky_open = is_finger_extended(20, 18, 17)

        # Normalized pinch distance (thumb tip to index tip relative to palm scale)
        raw_pinch_dist = float(np.linalg.norm(thumb_tip - index_tip))
        normalized_pinch_dist = raw_pinch_dist / palm_scale

        # 3D pointing ray direction (from index MCP through index Tip)
        pointing_raw = index_tip - index_mcp
        pointing_mag = np.linalg.norm(pointing_raw)
        pointing_vector = pointing_raw / pointing_mag if pointing_mag > 1e-5 else np.array([0.0, -1.0, 0.0])

        # Wrist roll angle relative to horizontal X-axis
        mcp_span = pinky_mcp - index_mcp
        wrist_roll_rad = float(math.atan2(mcp_span[1], mcp_span[0]))

        return HandPoseFeatures(
            palm_center=palm_center,
            palm_scale=palm_scale,
            palm_normal=palm_normal,
            is_thumb_open=is_thumb_open,
            is_index_open=is_index_open,
            is_middle_open=is_middle_open,
            is_ring_open=is_ring_open,
            is_pinky_open=is_pinky_open,
            pinch_distance=normalized_pinch_dist,
            pointing_vector=pointing_vector,
            wrist_roll_rad=wrist_roll_rad,
        )
