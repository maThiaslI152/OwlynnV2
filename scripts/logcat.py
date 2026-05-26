#!/usr/bin/env python3
"""
Owlynn audit log tail/filter tool.

Filters the rotating JSON-lines audit log (``audit.jsonl``) by channel,
log level, and thread ID. Supports ``--follow`` for live tailing.

Usage::

    python scripts/logcat.py --channel agent.model
    python scripts/logcat.py --channel agent.hitl --level WARN
    python scripts/logcat.py --thread-id abc-123
    python scripts/logcat.py --follow
    python scripts/logcat.py --channel memory
    python scripts/logcat.py --channel memory.cache,memory.ltm
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}
_LEVEL_LABELS = {v: k for k, v in _LOG_LEVELS.items()}


def _resolve_log_dir(args: argparse.Namespace) -> Path:
    """Return the audit log directory, respecting CLI override and env vars."""
    if args.log_dir:
        return Path(args.log_dir).expanduser().resolve()

    env_dir = os.environ.get("OWLYNN_AUDIT_LOG_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    # Try profile setting
    try:
        from src.memory.user_profile import get_profile
        profile = get_profile()
        audit_dir_str = profile.get("audit_log_dir", "")
        if audit_dir_str:
            return Path(audit_dir_str).expanduser().resolve()
    except Exception:
        pass

    return Path.home() / ".owlynn" / "logs"


def _channel_match(entry_channel: str, filters: list[str]) -> bool:
    """True if *entry_channel* matches any filter (exact or prefix)."""
    if not filters:
        return True
    for f in filters:
        f = f.strip()
        if not f:
            continue
        if entry_channel == f or entry_channel.startswith(f + "."):
            return True
    return False


def _level_from_entry(entry: dict) -> int:
    """Infer nominal log level from entry content (heuristic)."""
    event = entry.get("event", "")
    if "error" in event.lower() or "failed" in event.lower():
        return logging.ERROR
    if "warn" in event.lower() or "denied" in event.lower():
        return logging.WARNING
    if "debug" in event.lower() or event.startswith("edge_") or "cache_" in event:
        return logging.DEBUG
    return logging.INFO


def _color_for_level(level: int) -> str:
    """ANSI escape for log-level colouring."""
    if level >= logging.ERROR:
        return "\033[31m"  # red
    if level >= logging.WARNING:
        return "\033[33m"  # yellow
    if level <= logging.DEBUG:
        return "\033[90m"  # grey
    return "\033[0m"  # default


_RESET = "\033[0m"


def print_entry(entry: dict, args: argparse.Namespace) -> None:
    """Format and print a single audit log entry."""
    ts = entry.get("ts", "????-??-??T??:??:??.?")
    channel = entry.get("channel", "???")
    event = entry.get("event", "???")
    thread_id = entry.get("thread_id", "")
    level = _level_from_entry(entry)

    # Filter by level
    if args.level and level < _LOG_LEVELS.get(args.level.upper(), 0):
        return

    # Filter by thread_id
    if args.thread_id and thread_id != args.thread_id:
        return

    # Build compact display line
    color = "" if args.no_color else _color_for_level(level)
    level_label = _LEVEL_LABELS.get(level, "???")
    parts = [f"{color}{ts}", level_label, f"{channel}/{event}{_RESET}"]

    if thread_id:
        parts.insert(2, f"tid={thread_id}")

    # Show extra payload keys
    skip = {"ts", "channel", "event", "thread_id", "node", "route", "model"}
    extras = {k: v for k, v in entry.items() if k not in skip}
    if extras:
        parts.append(json.dumps(extras, ensure_ascii=False))

    print("  ".join(parts))


def cat_file(log_path: Path, args: argparse.Namespace) -> None:
    """Print filtered entries from a JSON-lines file."""
    if not log_path.exists():
        print(f"Audit log not found: {log_path}", file=sys.stderr)
        return

    channels = args.channel.split(",") if args.channel else []

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not _channel_match(entry.get("channel", ""), channels):
                continue
            print_entry(entry, args)


def follow_file(log_path: Path, args: argparse.Namespace) -> None:
    """Tail the audit log file, printing new entries as they appear."""
    channels = args.channel.split(",") if args.channel else []

    if not log_path.exists():
        print(f"Waiting for audit log: {log_path}", file=sys.stderr)
        while not log_path.exists():
            time.sleep(0.5)

    with open(log_path, "r", encoding="utf-8") as f:
        # Seek to end
        f.seek(0, os.SEEK_END)
        print(f"Following {log_path} (Ctrl+C to stop)", file=sys.stderr)
        try:
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.25)
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not _channel_match(entry.get("channel", ""), channels):
                    continue
                print_entry(entry, args)
        except KeyboardInterrupt:
            print("\nStopped.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tail and filter Owlynn audit logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --channel agent.model
  %(prog)s --channel agent.hitl --level WARN
  %(prog)s --thread-id abc-123
  %(prog)s --follow
  %(prog)s --channel memory
  %(prog)s --channel memory.cache,memory.ltm
""",
    )
    parser.add_argument(
        "--channel", "-c",
        help="Comma-separated channel names (exact or prefix match, e.g. 'memory' matches all memory.*)",
    )
    parser.add_argument(
        "--level", "-l",
        choices=["DEBUG", "INFO", "WARN", "WARNING", "ERROR"],
        help="Minimum log level to show",
    )
    parser.add_argument(
        "--thread-id", "-t",
        help="Filter by thread ID",
    )
    parser.add_argument(
        "--follow", "-f",
        action="store_true",
        help="Follow the log in real-time (like tail -f)",
    )
    parser.add_argument(
        "--log-dir", "-d",
        help="Path to audit log directory (overrides env var and profile)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colour output",
    )
    args = parser.parse_args()

    log_dir = _resolve_log_dir(args)
    log_path = log_dir / "audit.jsonl"

    if args.follow:
        follow_file(log_path, args)
    else:
        cat_file(log_path, args)


if __name__ == "__main__":
    main()
