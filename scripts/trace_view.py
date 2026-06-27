#!/usr/bin/env python3
"""
Owlynn conversation trace viewer.

Reads per-thread JSONL trace files and displays a human-readable timeline.
Designed for both human operators and IDE agents.

Usage::

    # List all traces
    python scripts/trace_view.py --list

    # View a specific thread
    python scripts/trace_view.py <thread_id>

    # View the latest trace
    python scripts/trace_view.py --latest

    # Filter by event type
    python scripts/trace_view.py <thread_id> --type router_decision,llm_response

    # JSON output (for IDE agents)
    python scripts/trace_view.py <thread_id> --json

    # Follow live trace
    python scripts/trace_view.py <thread_id> --follow
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path


def _resolve_trace_dir(args: argparse.Namespace) -> Path:
    if args.trace_dir:
        return Path(args.trace_dir).expanduser().resolve()
    return Path.home() / ".owlynn" / "traces"


_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_CYAN = "\033[36m"
_GRAY = "\033[90m"

_TYPE_STYLES: dict[str, str] = {
    "turn_start": _BOLD + _BLUE,
    "turn_end": _BOLD + _BLUE,
    "user_message": _BOLD + _GREEN,
    "router_decision": _CYAN,
    "llm_response": _YELLOW,
    "tool_call": _GRAY,
    "coherence_check": _DIM,
    "hitl_interrupt": _BOLD + _RED,
    "error": _BOLD + _RED,
    "trace_session_end": _DIM,
}


def _format_event(entry: dict, *, color: bool = True) -> str:
    ts = entry.get("ts", "")
    evt_type = entry.get("type", "???")
    style = _TYPE_STYLES.get(evt_type, "") if color else ""

    if evt_type == "turn_start":
        return f"{style}{'─' * 60}\n  ▶ Turn started{ts and f'  {ts}'}{_RESET}"

    if evt_type == "turn_end":
        return f"{style}  ■ Turn ended{ts and f'  {ts}'}\n{'─' * 60}{_RESET}"

    if evt_type == "user_message":
        content = entry.get("content", "")
        preview = content[:200] + ("..." if len(content) > 200 else "")
        return f"{style}  👤 User: {preview}{_RESET}"

    if evt_type == "router_decision":
        route = entry.get("route", "?")
        conf = entry.get("confidence", "?")
        src = entry.get("source", "")
        cat = entry.get("task_category", "")
        toolbox = entry.get("toolbox", "")
        parts = [f"route={route}", f"conf={conf}"]
        if src:
            parts.append(f"src={src}")
        if cat:
            parts.append(f"cat={cat}")
        if toolbox:
            parts.append(f"toolbox={toolbox}")
        return f"{style}  🔀 Router: {', '.join(parts)}{_RESET}"

    if evt_type == "llm_response":
        model = entry.get("model", "?")
        content = entry.get("content_preview", "")
        tc_count = entry.get("tool_call_count", 0)
        usage = entry.get("token_usage") or {}
        parts = [f"model={model}"]
        if tc_count:
            parts.append(f"tools={tc_count}")
        if usage:
            parts.append(f"tokens={usage.get('total_tokens', '?')}")
        preview = content[:150] + ("..." if len(content) > 150 else "")
        return f"{style}  🤖 LLM: {', '.join(parts)}\n     {preview}{_RESET}"

    if evt_type == "tool_call":
        name = entry.get("tool_name", "?")
        dur = entry.get("duration_s")
        err = entry.get("error")
        output = entry.get("output", "")
        status = f"{_RED}ERROR{_RESET}" if err else f"{_GREEN}OK{_RESET}"
        dur_str = f" ({dur:.1f}s)" if dur else ""
        preview = (err or output)[:150]
        return f"{style}  🔧 {name}: {status}{dur_str}\n     {preview}{_RESET}"

    if evt_type == "coherence_check":
        coh = entry.get("coherent", True)
        conf = entry.get("confidence", "?")
        reason = entry.get("reason", "")
        status = f"{_GREEN}coherent{_RESET}" if coh else f"{_RED}incoherent{_RESET}"
        return f"{style}  📊 Coherence: {status} (conf={conf}) {reason}{_RESET}"

    if evt_type == "hitl_interrupt":
        return (
            f"{style}  ⏸ HITL: {entry.get('interrupt_count', '?')} interrupts{_RESET}"
        )

    if evt_type == "error":
        return f"{style}  ✗ ERROR: {entry.get('message', '')}{_RESET}"

    if evt_type == "trace_session_end":
        return f"{style}{'─' * 40} trace end {'─' * 40}{_RESET}"

    # Fallback
    skip = {"ts", "type", "thread_id"}
    extras = {k: v for k, v in entry.items() if k not in skip}
    return (
        f"{style}  [{evt_type}] {json.dumps(extras, ensure_ascii=False)[:200]}{_RESET}"
    )


def list_traces(trace_dir: Path) -> None:
    if not trace_dir.exists():
        print(f"No traces directory: {trace_dir}")
        return
    files = sorted(
        trace_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not files:
        print("No traces found.")
        return
    for f in files:
        thread_id = f.stem
        size = f.stat().st_size
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        # Count lines
        try:
            with open(f) as fh:
                lines = sum(1 for _ in fh)
        except Exception:
            lines = "?"
        print(f"  {thread_id}  {lines} events  {size} bytes  {mtime}")


def view_trace(trace_dir: Path, thread_id: str, args: argparse.Namespace) -> None:
    path = trace_dir / f"{thread_id}.jsonl"
    if not path.exists():
        print(f"Trace not found: {path}", file=sys.stderr)
        sys.exit(1)

    type_filter = None
    if args.type:
        type_filter = set(t.strip() for t in args.type.split(","))

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if type_filter and entry.get("type") not in type_filter:
                continue
            if args.json:
                print(json.dumps(entry, ensure_ascii=False))
            else:
                print(_format_event(entry, color=not args.no_color))


def follow_trace(trace_dir: Path, thread_id: str, args: argparse.Namespace) -> None:
    path = trace_dir / f"{thread_id}.jsonl"
    if not path.exists():
        print(f"Waiting for trace: {path}", file=sys.stderr)
        while not path.exists():
            time.sleep(0.5)

    with open(path, encoding="utf-8") as f:
        f.seek(0, os.SEEK_END)
        print(f"Following trace {thread_id} (Ctrl+C to stop)", file=sys.stderr)
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
                if args.json:
                    print(json.dumps(entry, ensure_ascii=False))
                else:
                    print(_format_event(entry, color=not args.no_color))
        except KeyboardInterrupt:
            print("\nStopped.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="View Owlynn conversation traces",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list
  %(prog)s --latest
  %(prog)s thread-abc-123
  %(prog)s thread-abc-123 --type router_decision,llm_response
  %(prog)s thread-abc-123 --json
  %(prog)s thread-abc-123 --follow
""",
    )
    parser.add_argument("thread_id", nargs="?", help="Thread ID to view")
    parser.add_argument("--list", "-l", action="store_true", help="List all traces")
    parser.add_argument(
        "--latest", action="store_true", help="View the most recent trace"
    )
    parser.add_argument("--type", "-t", help="Comma-separated event types to show")
    parser.add_argument(
        "--json", "-j", action="store_true", help="Output raw JSON (for IDE agents)"
    )
    parser.add_argument(
        "--follow", "-f", action="store_true", help="Follow trace in real-time"
    )
    parser.add_argument("--trace-dir", "-d", help="Path to traces directory")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color")
    args = parser.parse_args()

    trace_dir = _resolve_trace_dir(args)

    if args.list:
        list_traces(trace_dir)
        return

    thread_id = args.thread_id
    if args.latest:
        files = sorted(
            trace_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        if not files:
            print("No traces found.", file=sys.stderr)
            sys.exit(1)
        thread_id = files[0].stem

    if not thread_id:
        parser.print_help()
        sys.exit(1)

    if args.follow:
        follow_trace(trace_dir, thread_id, args)
    else:
        view_trace(trace_dir, thread_id, args)


if __name__ == "__main__":
    main()
