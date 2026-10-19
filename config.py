import os
import sys

# Ensure backend can be imported
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from backend.config import settings, Settings

__all__ = ["settings", "Settings"]
