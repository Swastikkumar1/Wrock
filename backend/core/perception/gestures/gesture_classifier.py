from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
import time
import numpy as np
from .landmark_parser import HandPoseFeatures

class GestureType(str, Enum):
    IDLE = "IDLE"
    POINT = "POINT"
    PINCH_START = "PINCH_START"
    PINCH_HOLD = "PINCH_HOLD"
    PINCH_RELEASE = "PINCH_RELEASE"
    GRAB = "GRAB"
    OPEN_PALM = "OPEN_PALM"
    PUSH = "PUSH"
    SWIPE_LEFT = "SWIPE_LEFT"
    SWIPE_RIGHT = "SWIPE_RIGHT"
    SWIPE_UP = "SWIPE_UP"
    SWIPE_DOWN = "SWIPE_DOWN"
    WRIST_ROLL = "WRIST_ROLL"

@dataclass
class GestureEvent:
    gesture: GestureType
    confidence: float
    cursor_screen: Tuple[float, float, float]  # Normalized (x, y, z) [0..1]
    pointing_ray: Tuple[float, float, float]   # Normalized 3D directional vector
    pinch_distance: float
    wrist_roll_deg: float
    timestamp: float = field(default_factory=time.time)

class GestureClassifier:
    """
    Stateful gesture recognition pipeline adapting holo-gestures algorithms.
    Detects dynamic transitions (pinch onset, hold, release) and velocity swipes.
    """

    def __init__(
        self,
        pinch_enter_threshold: float = 0.28,
        pinch_exit_threshold: float = 0.38,
        velocity_window_size: int = 6,
        swipe_velocity_threshold: float = 1.2
    ):
        self.pinch_enter_threshold = pinch_enter_threshold
        self.pinch_exit_threshold = pinch_exit_threshold
        self.velocity_window_size = velocity_window_size
        self.swipe_velocity_threshold = swipe_velocity_threshold

        self._is_pinching: bool = False
        self._history_centers: List[Tuple[float, np.ndarray]] = []
        self._last_swipe_time: float = 0.0

    def classify(self, features: Optional[HandPoseFeatures]) -> GestureEvent:
        now = time.time()
        if features is None:
            return GestureEvent(
                gesture=GestureType.IDLE,
                confidence=0.0,
                cursor_screen=(0.5, 0.5, 0.0),
                pointing_ray=(0.0, 0.0, -1.0),
                pinch_distance=1.0,
                wrist_roll_deg=0.0,
                timestamp=now,
            )

        # Update position history for velocity and swipes
        self._history_centers.append((now, features.palm_center.copy()))
        if len(self._history_centers) > self.velocity_window_size:
            self._history_centers.pop(0)

        # Calculate velocity
        velocity = np.zeros(3, dtype=np.float32)
        if len(self._history_centers) >= 2:
            dt = self._history_centers[-1][0] - self._history_centers[0][0]
            if dt > 1e-4:
                dx = self._history_centers[-1][1] - self._history_centers[0][1]
                velocity = dx / dt

        # Screen cursor position (using index fingertip or palm center)
        cursor_x = float(features.palm_center[0])
        cursor_y = float(features.palm_center[1])
        cursor_z = float(features.palm_center[2])

        pointing_ray = (
            float(features.pointing_vector[0]),
            float(features.pointing_vector[1]),
            float(features.pointing_vector[2])
        )

        wrist_deg = float(np.degrees(features.wrist_roll_rad))
        pinch_dist = features.pinch_distance

        # Evaluate Pinch Transitions with Hysteresis
        current_gesture = GestureType.IDLE
        confidence = 0.85

        # Check swipe velocity (debounce: 400ms cooldown)
        if (now - self._last_swipe_time) > 0.4 and np.linalg.norm(velocity[:2]) > self.swipe_velocity_threshold:
            if abs(velocity[0]) > abs(velocity[1]):
                current_gesture = GestureType.SWIPE_RIGHT if velocity[0] > 0 else GestureType.SWIPE_LEFT
            else:
                current_gesture = GestureType.SWIPE_DOWN if velocity[1] > 0 else GestureType.SWIPE_UP
            self._last_swipe_time = now
            confidence = 0.95
        # Check Push gesture (z velocity moving into the screen/space)
        elif velocity[2] < -self.swipe_velocity_threshold * 0.8 and (now - self._last_swipe_time) > 0.4:
            current_gesture = GestureType.PUSH
            self._last_swipe_time = now
            confidence = 0.90
        # Check Pinch states
        elif not self._is_pinching and pinch_dist < self.pinch_enter_threshold:
            self._is_pinching = True
            current_gesture = GestureType.PINCH_START
            confidence = 0.98
        elif self._is_pinching:
            if pinch_dist > self.pinch_exit_threshold:
                self._is_pinching = False
                current_gesture = GestureType.PINCH_RELEASE
                confidence = 0.95
            else:
                current_gesture = GestureType.PINCH_HOLD
                confidence = 0.99
        # Check Grab / Fist: index, middle, ring, pinky closed
        elif (not features.is_index_open and 
              not features.is_middle_open and 
              not features.is_ring_open and 
              not features.is_pinky_open):
            current_gesture = GestureType.GRAB
            confidence = 0.92
        # Check Pointing: index extended, others curled
        elif (features.is_index_open and 
              not features.is_middle_open and 
              not features.is_ring_open and 
              not features.is_pinky_open):
            current_gesture = GestureType.POINT
            confidence = 0.96
        # Open Palm: all fingers extended
        elif (features.is_thumb_open and 
              features.is_index_open and 
              features.is_middle_open and 
              features.is_ring_open and 
              features.is_pinky_open):
            current_gesture = GestureType.OPEN_PALM
            confidence = 0.90

        return GestureEvent(
            gesture=current_gesture,
            confidence=confidence,
            cursor_screen=(cursor_x, cursor_y, cursor_z),
            pointing_ray=pointing_ray,
            pinch_distance=pinch_dist,
            wrist_roll_deg=wrist_deg,
            timestamp=now,
        )
