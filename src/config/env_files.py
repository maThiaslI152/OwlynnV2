"""Load project `.env` / `.env.local` into ``os.environ`` (mirrors ``start.sh``)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def load_project_env_files(project_root: Path | None = None) -> None:
    """Apply ``.env`` then ``.env.local``; local overrides base (like ``start.sh``)."""
    root = project_root or _REPO_ROOT
    try:
        from dotenv import load_dotenv
    except ImportError:
        _load_env_files_manual(root)
        return

    env_path = root / ".env"
    local_path = root / ".env.local"
    if env_path.is_file():
        load_dotenv(env_path, override=True)
    if local_path.is_file():
        load_dotenv(local_path, override=True)


def _load_env_files_manual(root: Path) -> None:
    """Fallback when python-dotenv is unavailable."""
    for name in (".env", ".env.local"):
        path = root / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key:
                os.environ[key] = val
