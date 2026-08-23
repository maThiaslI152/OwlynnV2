"""
Centralized file locking utility to prevent race conditions during concurrent
JSON file writes across async tasks and thread pools.
"""

import threading
from pathlib import Path

# Global registry of locks keyed by absolute file path
_locks: dict[str, threading.RLock] = {}
_registry_lock = threading.Lock()


def get_file_lock(file_path: Path | str) -> threading.RLock:
    """
    Get or create a threading.RLock for the specific file path.
    This ensures that concurrent threads (e.g. via asyncio.to_thread)
    do not clobber each other when writing to the same JSON file.
    """
    abs_path = str(Path(file_path).resolve())
    with _registry_lock:
        if abs_path not in _locks:
            _locks[abs_path] = threading.RLock()
        return _locks[abs_path]
