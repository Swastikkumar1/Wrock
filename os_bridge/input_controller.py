import time
import os
import sys
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Tuple

_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.005  # Ultra-low delay for responsive gesture tracking
except ImportError:
    pyautogui = None

try:
    from pynput import mouse as pynput_mouse
    from pynput import keyboard as pynput_keyboard
except ImportError:
    pynput_mouse = None
    pynput_keyboard = None

try:
    from backend.config import settings
except ImportError:
    from config import settings

logger = logging.getLogger("OSInputController")


class OSInputController:
    """
    Non-blocking, thread-safe OS input wrapper for desktop navigation,
    mouse tracking, and keyboard shortcuts via pyautogui/pynput.
    """

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="OSInput")
        self.screen_w, self.screen_h = (1920, 1080)
        if pyautogui:
            try:
                self.screen_w, self.screen_h = pyautogui.size()
            except Exception:
                pass

        # Pynput controllers
        self._pynput_mouse = pynput_mouse.Controller() if pynput_mouse else None
        self._pynput_kb = pynput_keyboard.Controller() if pynput_keyboard else None

        # Smooth cursor state
        self.smoothed_x: float = self.screen_w / 2.0
        self.smoothed_y: float = self.screen_h / 2.0
        self.last_emitted_x: float = self.screen_w / 2.0
        self.last_emitted_y: float = self.screen_h / 2.0
        self.is_dragging: bool = False
        self.pinch_start_time: Optional[float] = None

        # Cooldown trackers (timestamps)
        self.last_action_time: Dict[str, float] = {}

    def _is_cooling_down(self, action_key: str, cooldown_ms: Optional[int] = None) -> bool:
        cd = (cooldown_ms if cooldown_ms is not None else settings.GESTURE_COOLDOWN_MS) / 1000.0
        last = self.last_action_time.get(action_key, 0.0)
        return (time.time() - last) < cd

    def _mark_action(self, action_key: str):
        self.last_action_time[action_key] = time.time()

    # -------------------------------------------------------------
    # A. Cursor Tracking & Smoothing
    # -------------------------------------------------------------
    def move_cursor(self, norm_x: float, norm_y: float) -> Tuple[int, int]:
        """
        Maps normalized coordinates [0.0, 1.0] to desktop screen coordinates
        using Exponential Moving Average (EMA) and a deadzone filter to eliminate jitter.
        """
        if not pyautogui and not self._pynput_mouse:
            return (0, 0)

        # Clamp normalized inputs
        clamped_x = max(0.0, min(1.0, norm_x))
        clamped_y = max(0.0, min(1.0, norm_y))

        target_x = clamped_x * self.screen_w
        target_y = clamped_y * self.screen_h

        # Velocity-adaptive smoothing: heavy smoothing on micro-movements, instant tracking on fast moves
        dx = target_x - self.smoothed_x
        dy = target_y - self.smoothed_y
        dist = (dx * dx + dy * dy) ** 0.5

        base_alpha = getattr(settings, "SMOOTHING_FACTOR", 0.15)
        speed_factor = min(1.0, dist / 80.0)
        alpha = base_alpha + (0.45 - base_alpha) * (speed_factor ** 2)

        self.smoothed_x += alpha * dx
        self.smoothed_y += alpha * dy

        # Deadzone threshold check against last emitted position
        deadzone = getattr(settings, "DEADZONE_PIXELS", 4.0)
        dist_sq = (self.smoothed_x - self.last_emitted_x) ** 2 + (self.smoothed_y - self.last_emitted_y) ** 2

        if dist_sq >= (deadzone ** 2):
            self.last_emitted_x = self.smoothed_x
            self.last_emitted_y = self.smoothed_y
            int_x = int(round(self.smoothed_x))
            int_y = int(round(self.smoothed_y))

            # Move cursor directly
            try:
                if pyautogui:
                    pyautogui.moveTo(int_x, int_y)
                elif self._pynput_mouse:
                    self._pynput_mouse.position = (int_x, int_y)
            except Exception as e:
                logger.debug(f"Cursor move error: {e}")
            return (int_x, int_y)

        return (int(round(self.last_emitted_x)), int(round(self.last_emitted_y)))

    # -------------------------------------------------------------
    # B. Click & Drag Gestures
    # -------------------------------------------------------------
    def left_click(self):
        """Pinch index finger to thumb triggers Left Click."""
        if self._is_cooling_down("left_click", 250):
            return
        self._mark_action("left_click")

        def _action():
            executed = False
            if pyautogui:
                try:
                    pyautogui.click()
                    executed = True
                except Exception as e:
                    logger.debug(f"Left click error via pyautogui: {e}")
            if not executed and self._pynput_mouse:
                try:
                    self._pynput_mouse.click(pynput_mouse.Button.left)
                except Exception as e:
                    logger.debug(f"Left click error via pynput: {e}")

        self.executor.submit(_action)

    def right_click(self):
        """Pinch middle finger to thumb triggers Right Click."""
        if self._is_cooling_down("right_click", 400):
            return
        self._mark_action("right_click")

        def _action():
            executed = False
            if pyautogui:
                try:
                    pyautogui.rightClick()
                    executed = True
                except Exception as e:
                    logger.debug(f"Right click error via pyautogui: {e}")
            if not executed and self._pynput_mouse:
                try:
                    self._pynput_mouse.click(pynput_mouse.Button.right)
                except Exception as e:
                    logger.debug(f"Right click error via pynput: {e}")

        self.executor.submit(_action)

    def update_drag_state(self, is_pinching: bool):
        """
        Pinch held > 500ms engages drag-and-drop. Releasing unpinches.
        """
        now = time.time()
        hold_delay = getattr(settings, "DRAG_HOLD_DELAY_SEC", 0.50)

        if is_pinching:
            if self.pinch_start_time is None:
                self.pinch_start_time = now
            elif (now - self.pinch_start_time) >= hold_delay and not self.is_dragging:
                self.is_dragging = True
                self.executor.submit(self._engage_mouse_down)
        else:
            if self.is_dragging:
                self.is_dragging = False
                self.executor.submit(self._engage_mouse_up)
            self.pinch_start_time = None

    def _engage_mouse_down(self):
        try:
            if pyautogui:
                pyautogui.mouseDown()
            elif self._pynput_mouse:
                self._pynput_mouse.press(pynput_mouse.Button.left)
            logger.info("Drag engaged (mouseDown).")
        except Exception as e:
            logger.debug(f"mouseDown error: {e}")

    def _engage_mouse_up(self):
        try:
            if pyautogui:
                pyautogui.mouseUp()
            elif self._pynput_mouse:
                self._pynput_mouse.release(pynput_mouse.Button.left)
            logger.info("Drag released (mouseUp).")
        except Exception as e:
            logger.debug(f"mouseUp error: {e}")

    # -------------------------------------------------------------
    # C. Tab & Desktop Navigation
    # -------------------------------------------------------------
    def new_browser_tab(self):
        """Single-hand wave right: Trigger new browser tab (Ctrl + T)."""
        if self._is_cooling_down("new_tab", settings.GESTURE_COOLDOWN_MS):
            return
        self._mark_action("new_tab")

        def _action():
            try:
                if pyautogui:
                    pyautogui.hotkey("ctrl", "t")
                elif self._pynput_kb:
                    with self._pynput_kb.pressed(pynput_keyboard.Key.ctrl):
                        self._pynput_kb.tap('t')
                logger.info("Executed New Tab (Ctrl+T).")
            except Exception as e:
                logger.debug(f"Ctrl+T error: {e}")

        self.executor.submit(_action)

    def cycle_browser_tab(self):
        """Cycle to next tab (Ctrl + Tab)."""
        if self._is_cooling_down("cycle_tab", settings.GESTURE_COOLDOWN_MS):
            return
        self._mark_action("cycle_tab")

        def _action():
            try:
                if pyautogui:
                    pyautogui.hotkey("ctrl", "tab")
                elif self._pynput_kb:
                    with self._pynput_kb.pressed(pynput_keyboard.Key.ctrl):
                        self._pynput_kb.tap(pynput_keyboard.Key.tab)
                logger.info("Executed Cycle Tab (Ctrl+Tab).")
            except Exception as e:
                logger.debug(f"Ctrl+Tab error: {e}")

        self.executor.submit(_action)

    def switch_application(self):
        """Two-hand wave: Switch previous active app (Alt + Tab). Cooldown 600ms."""
        if self._is_cooling_down("app_switch", settings.GESTURE_COOLDOWN_MS):
            return
        self._mark_action("app_switch")

        def _action():
            try:
                if pyautogui:
                    pyautogui.hotkey("alt", "tab")
                elif self._pynput_kb:
                    self._pynput_kb.press(pynput_keyboard.Key.alt)
                    self._pynput_kb.tap(pynput_keyboard.Key.tab)
                    time.sleep(0.05)
                    self._pynput_kb.release(pynput_keyboard.Key.alt)
                logger.info("Executed Application Switch (Alt+Tab).")
            except Exception as e:
                logger.debug(f"Alt+Tab error: {e}")

        self.executor.submit(_action)

    # -------------------------------------------------------------
    # D. Universal Content Gestures (Zoom & Scroll)
    # -------------------------------------------------------------
    def zoom_in(self):
        """Increasing distance between two hands: Zoom In (Ctrl + Plus)."""
        if self._is_cooling_down("zoom_in", 200):
            return
        self._mark_action("zoom_in")

        def _action():
            try:
                if pyautogui:
                    pyautogui.hotkey("ctrl", "+")
                elif self._pynput_kb:
                    with self._pynput_kb.pressed(pynput_keyboard.Key.ctrl):
                        self._pynput_kb.tap('+')
            except Exception:
                try:
                    if pyautogui:
                        pyautogui.hotkey("ctrl", "add")
                except Exception as e:
                    logger.debug(f"Zoom in error: {e}")

        self.executor.submit(_action)

    def zoom_out(self):
        """Decreasing distance between two hands: Zoom Out (Ctrl + Minus)."""
        if self._is_cooling_down("zoom_out", 200):
            return
        self._mark_action("zoom_out")

        def _action():
            try:
                if pyautogui:
                    pyautogui.hotkey("ctrl", "-")
                elif self._pynput_kb:
                    with self._pynput_kb.pressed(pynput_keyboard.Key.ctrl):
                        self._pynput_kb.tap('-')
            except Exception:
                try:
                    if pyautogui:
                        pyautogui.hotkey("ctrl", "subtract")
                except Exception as e:
                    logger.debug(f"Zoom out error: {e}")

        self.executor.submit(_action)

    def scroll_page(self, direction: str = "up", amount: Optional[int] = None):
        """
        Two-finger vertical glide maps to continuous page scroll (Wheel Up / Wheel Down).
        """
        if self._is_cooling_down("scroll", 40):
            return
        self._mark_action("scroll")

        step = amount if amount is not None else settings.SCROLL_SENSITIVITY
        clicks = step if direction == "up" else -step

        def _action():
            if pyautogui:
                try:
                    pyautogui.scroll(clicks)
                except Exception as e:
                    logger.debug(f"Scroll error: {e}")

        self.executor.submit(_action)

    def horizontal_scrub(self, direction: str = "right"):
        """
        Two-finger horizontal glide maps to map panning or media player scrubbing.
        """
        if self._is_cooling_down("scrub", 120):
            return
        self._mark_action("scrub")

        key = "right" if direction == "right" else "left"

        def _action():
            if pyautogui:
                try:
                    pyautogui.press(key)
                except Exception as e:
                    logger.debug(f"Scrub error: {e}")

        self.executor.submit(_action)

    def shutdown(self):
        self.executor.shutdown(wait=False)
