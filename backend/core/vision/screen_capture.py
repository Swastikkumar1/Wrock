"""Re-export from core.vision.screen_capture for backend.core.vision compatibility."""
from core.vision.screen_capture import (
    capture_full_screen,
    capture_active_window,
    capture_screen_base64,
    get_active_window_info,
    image_to_base64,
    resize_image_in_memory,
)

__all__ = [
    "capture_full_screen",
    "capture_active_window",
    "capture_screen_base64",
    "get_active_window_info",
    "image_to_base64",
    "resize_image_in_memory",
]
