#!/usr/bin/env python3
"""Clean up stale study sessions (quiz sessions older than 30 days)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
QUIZ_DIR = DATA_DIR / "quiz_sessions"
ARCHIVE_DIR = DATA_DIR / "quiz_archive"


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


def cleanup_stale_sessions(max_age_days: int = 30, dry_run: bool = False) -> None:
    """Archive quiz sessions older than max_age_days."""
    if not QUIZ_DIR.is_dir():
        print("No quiz sessions directory found.")
        return

    cutoff = datetime.now() - timedelta(days=max_age_days)
    cutoff_str = cutoff.isoformat(timespec="seconds")

    sessions = list(QUIZ_DIR.glob("*.json"))
    stale = []
    active = []

    for path in sessions:
        session = read_json(path, {})
        started = session.get("started_at", "")
        if started and started < cutoff_str:
            stale.append((path, session))
        else:
            active.append(path)

    print(f"Found {len(sessions)} sessions: {len(stale)} stale, {len(active)} active")

    if not stale:
        print("No stale sessions to clean up.")
        return

    if dry_run:
        print("\n[DRY RUN] Would archive:")
        for path, session in stale:
            print(
                f"  {path.name}: {session.get('topic', '?')} ({session.get('started_at', '?')})"
            )
        return

    # Archive stale sessions
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    for path, session in stale:
        archive_path = ARCHIVE_DIR / path.name
        write_json(archive_path, session)
        path.unlink()
        print(f"  Archived: {path.name}")

    print(f"\nArchived {len(stale)} sessions to {ARCHIVE_DIR}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Clean up stale study sessions")
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=30,
        help="Archive sessions older than this (default: 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without making changes",
    )
    args = parser.parse_args()

    cleanup_stale_sessions(args.max_age_days, args.dry_run)


if __name__ == "__main__":
    main()
