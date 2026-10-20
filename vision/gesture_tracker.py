import math
import time
import os
import sys
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Callable

_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

try:
    import cv2
except ImportError:
    cv2 = None

mp = None
mp_hands = None

def _get_mp_hands():
    global mp, mp_hands
    if mp_hands is None:
        try:
            import mediapipe as _mp
            mp = _mp
            mp_hands = _mp.solutions.hands
        except Exception as e:
            logger.warning(f"MediaPipe hands unavailable: {e}")
            mp = None
            mp_hands = None
    return mp_hands

try:
    from backend.config import settings
except ImportError:
    from config import settings

from os_bridge.input_controller import OSInputController

logger = logging.getLogger("GestureTracker")


@dataclass
class HandPoseFrame:
    timestamp: float
    landmarks: List[Dict[str, float]]  # 21 points with x, y, z
    handedness: str = "Right"          # "Right" or "Left"


class GestureTracker:
    """
    Vision-based full-system gesture control engine using OpenCV & MediaPipe Hands.
    Processes live video frames or incoming landmark streams to drive OS-level inputs
    (cursor motion, left/right clicks, drag-and-drop, tab navigation, zooming, and scrolling).
    """

    def __init__(self, input_controller: Optional[OSInputController] = None):
        self.input_controller = input_controller or OSInputController()
        self.is_running: bool = False

        # MediaPipe Hands detector (initialized lazily when camera starts)
        self.hands_detector = None

        # State machines & history buffers
        # 1. Single-hand swipe detection (rolling window of wrist x coordinates)
        self.wrist_history: deque = deque(maxlen=15)  # (time, x)
        self.last_swipe_time: float = 0.0

        # 2. Two-hand tracking buffers
        self.last_two_hand_dist: Optional[float] = None
        self.two_hand_wrist_history: deque = deque(maxlen=15)  # (time, lx, rx)

        # 3. Two-finger scroll tracking
        self.prev_scroll_y: Optional[float] = None
        self.prev_scroll_x: Optional[float] = None

        # 4. Drag & Drop and Double-Pinch Left Click state
        self.pinch_active: bool = False
        self.was_index_pinching: bool = False
        self.last_pinch_release_time: float = 0.0

        # Telemetry callback for HUD synchronization
        self.on_gesture_telemetry: Optional[Callable[[str, Dict[str, Any]], None]] = None

    def _ensure_hands_detector(self):
        if self.hands_detector is None:
            hands_mod = _get_mp_hands()
            if hands_mod:
                try:
                    self.hands_detector = hands_mod.Hands(
                        static_image_mode=False,
                        max_num_hands=2,
                        min_detection_confidence=0.65,
                        min_tracking_confidence=0.60,
                    )
                except Exception as e:
                    logger.warning(f"Could not initialize MediaPipe Hands: {e}")
        return self.hands_detector

    # -------------------------------------------------------------
    # Frame Processing (OpenCV / Camera)
    # -------------------------------------------------------------
    def process_camera_frame(self, frame_bgr) -> Dict[str, Any]:
        """
        Processes a raw BGR camera frame from OpenCV through MediaPipe Hands.
        """
        detector = self._ensure_hands_detector()
        if not detector or frame_bgr is None:
            return {"active": False}

        # Flip horizontally for natural mirror behavior
        flipped = cv2.flip(frame_bgr, 1)
        rgb_frame = cv2.cvtColor(flipped, cv2.COLOR_BGR2RGB)
        rgb_frame.flags.writeable = False

        results = detector.process(rgb_frame)
        rgb_frame.flags.writeable = True

        hands_list: List[HandPoseFrame] = []
        now = time.time()

        if results.multi_hand_landmarks:
            for idx, hand_lms in enumerate(results.multi_hand_landmarks):
                handedness_label = "Right"
                if results.multi_handedness and idx < len(results.multi_handedness):
                    handedness_label = results.multi_handedness[idx].classification[0].label

                lms = [{"x": pt.x, "y": pt.y, "z": pt.z} for pt in hand_lms.landmark]
                hands_list.append(HandPoseFrame(timestamp=now, landmarks=lms, handedness=handedness_label))

        return self.process_hands(hands_list)

    # -------------------------------------------------------------
    # Core Multi-Hand Gesture State Machine
    # -------------------------------------------------------------
    def process_hands(self, hands: List[HandPoseFrame]) -> Dict[str, Any]:
        """
        Main gesture state machine evaluating:
        - Cursor movement (Index tip)
        - Left click (Index pinch)
        - Right click (Middle pinch)
        - Drag-and-drop (>500ms pinch hold)
        - Single-hand wave (Right swipe -> new tab / cycle tab)
        - Two-hand wave (App switch)
        - Two-hand pinch zoom (Expand -> zoom in, contract -> zoom out)
        - Two-finger vertical scroll & horizontal scrub
        """
        now = hands[0].timestamp if hands and getattr(hands[0], 'timestamp', None) else time.time()
        num_hands = len(hands)
        telemetry = {
            "num_hands": num_hands,
            "gesture": "IDLE",
            "cursor": (0, 0),
            "timestamp": now,
        }

        if num_hands == 0:
            # Reset pinch/drag states when hands leave frame
            if self.pinch_active:
                self.pinch_active = False
                self.input_controller.update_drag_state(False)
            self.was_index_pinching = False
            self.last_two_hand_dist = None
            self.prev_scroll_y = None
            self.prev_scroll_x = None
            return telemetry

        # =========================================================
        # 1. TWO-HAND GESTURES (When 2 hands are detected)
        # =========================================================
        if num_hands >= 2:
            hand_1 = hands[0].landmarks
            hand_2 = hands[1].landmarks

            # Index tips for both hands: point 8
            idx1 = hand_1[8]
            idx2 = hand_2[8]
            two_hand_dist = math.hypot(idx1["x"] - idx2["x"], idx1["y"] - idx2["y"])

            # A. Two-Hand Distance Tracking: Zoom In / Zoom Out
            zoom_thresh = getattr(settings, "TWO_HAND_ZOOM_THRESHOLD", 0.035)
            if self.last_two_hand_dist is not None:
                dist_delta = two_hand_dist - self.last_two_hand_dist
                if dist_delta > zoom_thresh:
                    self.input_controller.zoom_in()
                    telemetry["gesture"] = "TWO_HAND_ZOOM_IN"
                    self._emit_telemetry("ZOOM_IN", {"delta": dist_delta})
                elif dist_delta < -zoom_thresh:
                    self.input_controller.zoom_out()
                    telemetry["gesture"] = "TWO_HAND_ZOOM_OUT"
                    self._emit_telemetry("ZOOM_OUT", {"delta": dist_delta})

            self.last_two_hand_dist = two_hand_dist

            # B. Two-Hand Wave: Horizontal Synchronous Swipe -> Alt + Tab
            wrist1_x = hand_1[0]["x"]
            wrist2_x = hand_2[0]["x"]
            self.two_hand_wrist_history.append((now, wrist1_x, wrist2_x))

            if len(self.two_hand_wrist_history) >= 6:
                t_old, old_w1, old_w2 = self.two_hand_wrist_history[0]
                dt = now - t_old
                if 0.05 < dt < 0.60:
                    v1 = (wrist1_x - old_w1) / dt
                    v2 = (wrist2_x - old_w2) / dt
                    # If both hands moved swiftly in the same horizontal direction
                    if (v1 > 0.40 and v2 > 0.40) or (v1 < -0.40 and v2 < -0.40):
                        self.input_controller.switch_application()
                        telemetry["gesture"] = "TWO_HAND_WAVE_SWITCH_APP"
                        self._emit_telemetry("APP_SWITCH", {"v1": v1, "v2": v2})
                        self.two_hand_wrist_history.clear()

            return telemetry

        # Reset two-hand distance when single hand present
        self.last_two_hand_dist = None

        # =========================================================
        # 2. SINGLE-HAND GESTURES (Primary Hand)
        # =========================================================
        primary = hands[0].landmarks

        wrist = primary[0]
        thumb_tip = primary[4]
        index_tip = primary[8]
        middle_tip = primary[12]
        ring_tip = primary[16]
        pinky_tip = primary[20]

        index_mcp = primary[5]
        middle_mcp = primary[9]

        # Finger extension tests
        index_extended = index_tip["y"] < primary[6]["y"]
        middle_extended = middle_tip["y"] < primary[10]["y"]
        ring_folded = ring_tip["y"] > primary[14]["y"]
        pinky_folded = pinky_tip["y"] > primary[18]["y"]

        # Pinch distances
        pinch_index_dist = math.hypot(index_tip["x"] - thumb_tip["x"], index_tip["y"] - thumb_tip["y"])
        pinch_middle_dist = math.hypot(middle_tip["x"] - thumb_tip["x"], middle_tip["y"] - thumb_tip["y"])

        pinch_thresh = getattr(settings, "PINCH_THRESHOLD", 0.045)
        middle_pinch_thresh = getattr(settings, "MIDDLE_PINCH_THRESHOLD", 0.048)

        # A. Single-Hand Wave (Left-to-Right Swipe -> New Tab or Cycle Tab)
        self.wrist_history.append((now, wrist["x"]))
        if len(self.wrist_history) >= 8:
            t_old, x_old = self.wrist_history[0]
            dt = now - t_old
            if 0.08 < dt < 0.50:
                vel_x = (wrist["x"] - x_old) / dt
                swipe_thresh = getattr(settings, "SWIPE_VELOCITY_THRESHOLD", 0.07)
                if vel_x > swipe_thresh * 10:  # Moving right
                    # Check if consecutive swipe (cycle tab) or initial swipe (new tab)
                    if (now - self.last_swipe_time) < 2.0:
                        self.input_controller.cycle_browser_tab()
                        telemetry["gesture"] = "SWIPE_RIGHT_CYCLE_TAB"
                    else:
                        self.input_controller.new_browser_tab()
                        telemetry["gesture"] = "SWIPE_RIGHT_NEW_TAB"

                    self.last_swipe_time = now
                    self.wrist_history.clear()
                    self._emit_telemetry(telemetry["gesture"], {"velocity_x": vel_x})
                    return telemetry

        # B. Two-Finger Scroll / Slide (Index + Middle extended, Ring + Pinky folded)
        if index_extended and middle_extended and ring_folded and pinky_folded:
            mid_y = (index_tip["y"] + middle_tip["y"]) / 2.0
            mid_x = (index_tip["x"] + middle_tip["x"]) / 2.0

            if self.prev_scroll_y is not None:
                dy = mid_y - self.prev_scroll_y
                dx = mid_x - self.prev_scroll_x

                # Vertical scroll
                if abs(dy) > 0.012:
                    direction = "down" if dy > 0 else "up"
                    self.input_controller.scroll_page(direction=direction)
                    telemetry["gesture"] = f"TWO_FINGER_SCROLL_{direction.upper()}"

                # Horizontal scrub / pan
                elif abs(dx) > 0.022:
                    direction = "right" if dx > 0 else "left"
                    self.input_controller.horizontal_scrub(direction=direction)
                    telemetry["gesture"] = f"TWO_FINGER_SCRUB_{direction.upper()}"

            self.prev_scroll_y = mid_y
            self.prev_scroll_x = mid_x
            return telemetry
        else:
            self.prev_scroll_y = None
            self.prev_scroll_x = None

        # C. Right Click: Pinch Middle finger to Thumb
        if pinch_middle_dist < middle_pinch_thresh and pinch_index_dist > pinch_thresh * 1.3:
            self.input_controller.right_click()
            telemetry["gesture"] = "RIGHT_CLICK"
            self._emit_telemetry("RIGHT_CLICK", {"dist": pinch_middle_dist})
            return telemetry

        # D. Double-Pinch Left Click & Drag: Pinch Index finger to Thumb twice within double-pinch window
        is_index_pinching = pinch_index_dist < pinch_thresh
        self.pinch_active = is_index_pinching

        # Update Drag & Drop (>500ms hold)
        self.input_controller.update_drag_state(is_index_pinching)

        is_pinch_start = is_index_pinching and not self.was_index_pinching
        is_pinch_release = (not is_index_pinching) and self.was_index_pinching

        if is_pinch_start:
            double_pinch_window = getattr(settings, "DOUBLE_PINCH_WINDOW_SEC", 0.55)
            # If a prior pinch was released recently within double_pinch_window -> Double Pinch = Left Click!
            if self.last_pinch_release_time > 0 and (now - self.last_pinch_release_time) <= double_pinch_window:
                self.input_controller.left_click()
                telemetry["gesture"] = "LEFT_CLICK"
                self._emit_telemetry("LEFT_CLICK", {"dist": pinch_index_dist})
                self.last_pinch_release_time = 0.0  # Reset so subsequent third pinch doesn't click again immediately
            else:
                telemetry["gesture"] = "PINCH_START"
                self._emit_telemetry("PINCH_START", {"dist": pinch_index_dist})
        elif is_index_pinching:
            if self.input_controller.is_dragging:
                telemetry["gesture"] = "DRAGGING"
            elif telemetry["gesture"] != "LEFT_CLICK":
                telemetry["gesture"] = "PINCH_HELD"

        if is_pinch_release:
            self.last_pinch_release_time = now
            telemetry["gesture"] = "PINCH_RELEASE"
            self._emit_telemetry("PINCH_RELEASE", {"timestamp": now})

        self.was_index_pinching = is_index_pinching

        # E. Cursor Movement: Index Fingertip (only when pointing/extended or actively pinching/dragging)
        if index_extended or self.pinch_active or self.input_controller.is_dragging:
            sx, sy = self.input_controller.move_cursor(index_tip["x"], index_tip["y"])
            telemetry["cursor"] = (sx, sy)
            if telemetry["gesture"] == "IDLE":
                telemetry["gesture"] = "CURSOR_MOVE"

        return telemetry

    def _emit_telemetry(self, gesture_name: str, payload: Dict[str, Any]):
        if self.on_gesture_telemetry:
            try:
                self.on_gesture_telemetry(gesture_name, payload)
            except Exception:
                pass

    # -------------------------------------------------------------
    # 3. Dedicated Background Camera Capture Thread (OpenCV)
    # -------------------------------------------------------------
    def start_background_camera(self, camera_index: Optional[int] = None) -> bool:
        """
        Launches a background daemon thread capturing from OpenCV VideoCapture
        and driving OS-level gesture automation.
        """
        import threading

        if self.is_running:
            logger.info("Background camera capture already running.")
            return True

        if cv2 is None:
            logger.warning("OpenCV (cv2) not available for camera capture.")
            return False

        idx = camera_index if camera_index is not None else getattr(settings, "CAMERA_INDEX", 0)
        self.is_running = True

        def _camera_worker():
            logger.info(f"Starting OpenCV Camera Capture on device index {idx}...")
            cap = cv2.VideoCapture(idx)
            if not cap.isOpened():
                # Try fallback DirectShow backend on Windows
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)

            if not cap.isOpened():
                logger.warning(f"Could not open camera {idx}. Camera may be in use by browser HUD or unavailable.")
                self.is_running = False
                return

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)

            logger.info(f"OpenCV Camera {idx} successfully opened. Processing gestures...")

            try:
                while self.is_running:
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        time.sleep(0.01)
                        continue

                    self.process_camera_frame(frame)
                    time.sleep(0.01)  # ~30 FPS loop
            except Exception as e:
                logger.error(f"Error in camera loop: {e}", exc_info=True)
            finally:
                cap.release()
                self.is_running = False
                logger.info("OpenCV Camera released.")

        cam_thread = threading.Thread(target=_camera_worker, name="GestureCameraThread", daemon=True)
        cam_thread.start()
        return True

    def stop_background_camera(self):
        """Stops the OpenCV camera capture thread."""
        self.is_running = False
        logger.info("Stopping background camera capture...")

    def release(self):
        self.stop_background_camera()
        if self.hands_detector:
            try:
                self.hands_detector.close()
            except Exception:
                pass


if __name__ == "__main__":
    import sys
    print("Testing GestureTracker standalone...")
    gt = GestureTracker()
    print("GestureTracker initialized successfully.")
    if "--cam" in sys.argv:
        gt.start_background_camera(0)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            gt.release()
            print("Stopped.")

