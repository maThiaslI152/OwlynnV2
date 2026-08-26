#!/usr/bin/env python3
"""Live WS E2E: same-thread topic drift with web_search + workspace tools.

Realistic conversation: Thailand capital → GDP → weather digression →
write a note to workspace → list/read it → return to GDP follow-up.

Logs per-turn: ttft_ms, elapsed_s, route, tools, errors, tool-leak, idle.
Writes JSON report to /tmp/e2e_topic_drift_result.json

  uv run python scripts/manual/e2e_topic_drift_ws.py

Uses WebSocket ``idle`` as turn completion (not DOM polling).
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import websockets

API_URL = "http://127.0.0.1:8000"
TURN_TIMEOUT_S = 300
OUT_PATH = Path("/tmp/e2e_topic_drift_result.json")
TOOL_LEAK_RE = re.compile(
    r"<\|?tool_call|GoogleSearch|<function=|</tool_call>", re.IGNORECASE
)

# SLO bands from docs/PERFORMANCE_SLOS.md (warm local_only targets)
SLO = {
    "simple_ttft_ms": 2000,
    "simple_turn_s": 3.0,
    "simple_unacceptable_s": 8.0,
    "web_turn_s": 8.0,
    "web_unacceptable_s": 25.0,
    "complex_turn_s": 20.0,
    "complex_unacceptable_s": 60.0,
    "tool_s": 5.0,
}


def _parse_args(argv: list[str] | None = None) -> Any:
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--profile",
        choices=("full", "usable"),
        default="full",
        help="full=6 turn topic drift; usable=simple→web→write (3 turns)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=OUT_PATH,
        help="JSON report path",
    )
    return p.parse_args(argv)


async def _get_token() -> str:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{API_URL}/api/local-run-token")
        r.raise_for_status()
        token = r.json().get("token") or ""
        if not token:
            raise RuntimeError("empty local run token")
        return token


def _assistant_text(event: dict) -> str:
    msg = event.get("message")
    if isinstance(msg, dict):
        content = msg.get("content") or ""
    else:
        content = event.get("content") or ""
    return content if isinstance(content, str) else str(content or "")


def _route_from(meta: dict | None) -> str:
    if not isinstance(meta, dict):
        return ""
    return str(meta.get("route") or meta.get("final_route") or "")


async def _run_turn(
    ws: Any,
    *,
    message: str,
    thread_id: str,
    project_id: str,
    label: str,
    expect: dict[str, Any],
) -> dict[str, Any]:
    print(f"\n── {label} ──")
    print(f"  USER: {message}")
    since = time.monotonic()
    await ws.send(
        json.dumps(
            {
                "message": message,
                "files": [],
                "mode": "tools_on",
                "web_search_enabled": True,
                "project_id": project_id,
                "thread_id": thread_id,
                "scenario_id": None,
            }
        )
    )

    tools: list[str] = []
    tool_durations: dict[str, float] = {}
    tool_started: dict[str, float] = {}
    router_meta: dict | None = None
    assistant = ""
    chunks: list[str] = []
    statuses: list[str] = []
    errors: list[str] = []
    idle = False
    ttft_ms: int | None = None
    timed_out = False

    try:
        while True:
            remaining = TURN_TIMEOUT_S - (time.monotonic() - since)
            if remaining <= 0:
                timed_out = True
                raise TimeoutError(f"{label}: no idle within {TURN_TIMEOUT_S}s")
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            event = json.loads(raw)
            etype = event.get("type")

            if etype == "status":
                st = event.get("content") or ""
                statuses.append(st)
                print(f"  [status] {st}")
                if st == "idle":
                    idle = True
                    break
            elif etype == "router_info":
                router_meta = event.get("metadata") or event
                route = _route_from(
                    router_meta if isinstance(router_meta, dict) else None
                )
                src = (
                    (router_meta or {}).get("classification_source")
                    if isinstance(router_meta, dict)
                    else None
                )
                print(f"  [router] route={route} source={src}")
            elif etype == "tool_execution":
                name = (event.get("tool_name") or "").strip()
                st = event.get("status") or ""
                if name:
                    tools.append(f"{name}:{st}")
                    if st == "running":
                        tool_started[name] = time.monotonic()
                    elif st in ("success", "error") and name in tool_started:
                        tool_durations[name] = time.monotonic() - tool_started[name]
                dur = event.get("duration")
                print(f"  [tool] {name} → {st}" + (f" ({dur}s)" if dur else ""))
            elif etype == "chunk":
                part = event.get("content") or ""
                if part:
                    if ttft_ms is None:
                        ttft_ms = int((time.monotonic() - since) * 1000)
                    chunks.append(part)
            elif etype == "assistant.message":
                assistant = _assistant_text(event)
                preview = (assistant or "")[:160].replace("\n", " ")
                print(f"  [assistant] {preview!r}...")
            elif etype == "error":
                err = str(event.get("content") or event)
                errors.append(err)
                print(f"  [error] {err[:200]}")
            elif etype == "interrupt":
                items = event.get("interrupts") or []
                kind = ""
                if items and isinstance(items[0], dict):
                    value = items[0].get("value") or items[0]
                    if isinstance(value, dict):
                        kind = str(value.get("type") or "")
                print(f"  [interrupt] HITL kind={kind or 'unknown'} — auto-resolving")
                if kind in (
                    "security_approval_required",
                    "plan_review_required",
                    "security_approval",
                ):
                    await ws.send(
                        json.dumps(
                            {
                                "type": "security_approval"
                                if "security" in kind
                                else "plan_review_response",
                                "approved": True,
                                "feedback": "e2e auto-approve",
                                "correlation_id": str(uuid.uuid4()),
                            }
                        )
                    )
                else:
                    await ws.send(
                        json.dumps(
                            {
                                "type": "ask_user_response",
                                "answer": {"skipped": True},
                                "correlation_id": str(uuid.uuid4()),
                            }
                        )
                    )
    except TimeoutError as exc:
        errors.append(str(exc))
        print(f"  [TIMEOUT] {exc}")

    text = assistant or "".join(chunks)
    elapsed = time.monotonic() - since
    tool_names = sorted({t.split(":")[0] for t in tools if t})
    leak = bool(TOOL_LEAK_RE.search(text or ""))
    route = _route_from(router_meta)

    # Soft expectations
    failures: list[str] = []
    if timed_out or not idle:
        failures.append("no_idle")
    if leak:
        failures.append("tool_leak")
    if errors and not all("Timeout" in e for e in errors):
        failures.append("ws_error")
    if expect.get("min_chars") and len((text or "").strip()) < int(expect["min_chars"]):
        failures.append("short_answer")
    must_tools = expect.get("must_tools") or []
    for t in must_tools:
        if t not in tool_names:
            failures.append(f"missing_tool:{t}")
    forbid_tools = expect.get("forbid_tools") or []
    for t in forbid_tools:
        if t in tool_names:
            failures.append(f"unexpected_tool:{t}")
    must_route_prefix = expect.get("route_not_prefix")
    if must_route_prefix and route.startswith(must_route_prefix):
        failures.append(f"bad_route:{route}")
    expect_route_contains = expect.get("route_contains")
    if expect_route_contains and route and expect_route_contains not in route:
        failures.append(f"route_mismatch:{route}")
    must_substrings = expect.get("text_any") or []
    if must_substrings:
        lower = (text or "").lower()
        if not any(s.lower() in lower for s in must_substrings):
            failures.append("text_missing_keywords")

    kind = expect.get("kind", "complex")
    band = "ok"
    if kind == "simple":
        if elapsed > SLO["simple_unacceptable_s"]:
            band = "unacceptable"
        elif elapsed > SLO["simple_turn_s"]:
            band = "degraded"
        if ttft_ms and ttft_ms > SLO["simple_ttft_ms"] * 4:
            band = "unacceptable" if band == "ok" else band
    elif kind == "web":
        if elapsed > SLO["web_unacceptable_s"]:
            band = "unacceptable"
        elif elapsed > SLO["web_turn_s"]:
            band = "degraded"
    else:
        if elapsed > SLO["complex_unacceptable_s"]:
            band = "unacceptable"
        elif elapsed > SLO["complex_turn_s"]:
            band = "degraded"

    print(
        f"  done in {elapsed:.1f}s | ttft_ms={ttft_ms} | route={route or '-'} | "
        f"tools={tool_names} | band={band} | fail={failures or 'none'}"
    )
    return {
        "label": label,
        "message": message,
        "kind": kind,
        "elapsed_s": round(elapsed, 2),
        "ttft_ms": ttft_ms,
        "idle": idle,
        "timed_out": timed_out,
        "tools": tools,
        "tool_names": tool_names,
        "tool_durations_s": {k: round(v, 2) for k, v in tool_durations.items()},
        "route": route,
        "router": {
            k: router_meta.get(k)
            for k in ("route", "classification_source", "reasoning", "confidence")
            if isinstance(router_meta, dict) and k in router_meta
        },
        "text": text,
        "text_preview": (text or "")[:300],
        "chars": len(text or ""),
        "statuses": statuses,
        "errors": errors,
        "tool_leak": leak,
        "slo_band": band,
        "failures": failures,
        "passed": not failures,
    }


async def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    out_path: Path = args.out
    profile: str = args.profile

    health = httpx.get(f"{API_URL}/api/health", timeout=5.0)
    health.raise_for_status()
    print(f"[e2e] health={health.json()} profile={profile}")

    token = await _get_token()
    run_nonce = uuid.uuid4().hex[:10]
    thread_id = f"thread-e2e-drift-{run_nonce}"
    project_id = f"e2e-drift-{run_nonce}"
    ws_url = f"ws://127.0.0.1:8000/ws/chat/{thread_id}?token={token}"
    print(f"[e2e] thread={thread_id} project={project_id}")

    note_name = f"bangkok_notes_{run_nonce}.txt"
    turns_spec: list[dict[str, Any]] = [
        {
            "label": "T1 capital (simple)",
            "message": "what is the capital city of Thailand",
            "expect": {
                "kind": "simple",
                "min_chars": 5,
                "text_any": ["bangkok"],
                "forbid_tools": ["web_search"],
            },
        },
        {
            "label": "T2 GDP follow-up (web)",
            "message": f"what is it's GDP roughly? [eval-nonce={run_nonce}]",
            "expect": {
                "kind": "web",
                "min_chars": 40,
                "must_tools": ["web_search"],
                "text_any": ["gdp", "billion", "economy", "baht", "dollar"],
                "route_not_prefix": "simple",
            },
        },
        {
            "label": "T3 weather digression (web)",
            "message": (
                f"anyway what's the weather in Bangkok right now? "
                f"[eval-nonce={run_nonce}-wx]"
            ),
            "expect": {
                "kind": "web",
                "min_chars": 30,
                "must_tools": ["web_search"],
                "text_any": ["c", "°", "temp", "rain", "humid", "weather", "bangkok"],
            },
        },
        {
            "label": "T4 write workspace note (file tool)",
            "message": (
                f"Save a short note to my workspace as {note_name} summarizing "
                f"Bangkok capital + that we asked about GDP and weather. "
                f"Use write_workspace_file. Keep it under 80 words. "
                f"[eval-nonce={run_nonce}-write]"
            ),
            "expect": {
                "kind": "complex",
                "min_chars": 0,
                "must_tools": ["write_workspace_file"],
            },
        },
        {
            "label": "T5 list/read note (file tool)",
            "message": (
                f"List workspace files and read {note_name} back to me. "
                f"[eval-nonce={run_nonce}-read]"
            ),
            "expect": {
                "kind": "complex",
                "min_chars": 20,
                # either list or read is progress; prefer both
                "must_tools": [],
                "text_any": [
                    "bangkok",
                    note_name.replace(".txt", ""),
                    "gdp",
                    "weather",
                ],
            },
        },
        {
            "label": "T6 back to GDP (web, same thread)",
            "message": (
                f"ok back to economics — is Thailand's GDP growing this year? "
                f"[eval-nonce={run_nonce}-gdp2]"
            ),
            "expect": {
                "kind": "web",
                "min_chars": 40,
                "must_tools": ["web_search"],
                "text_any": ["gdp", "growth", "percent", "%", "economy", "forecast"],
            },
        },
    ]
    if profile == "usable":
        # Critical path for daily use: simple → web follow-up → workspace write.
        turns_spec = [turns_spec[0], turns_spec[1], turns_spec[3]]

    results: list[dict[str, Any]] = []
    async with websockets.connect(ws_url, max_size=16 * 1024 * 1024) as ws:
        for spec in turns_spec:
            turn = await _run_turn(
                ws,
                message=spec["message"],
                thread_id=thread_id,
                project_id=project_id,
                label=spec["label"],
                expect=spec["expect"],
            )
            results.append(turn)

    # Soft check T5 tools after the fact
    t5 = next((r for r in results if r["label"].startswith("T5")), None)
    if t5 is not None:
        names = set(t5["tool_names"])
        if not names.intersection(
            {
                "list_workspace_files",
                "read_workspace_file",
                "list_workspace",
                "read_file",
            }
        ):
            # accept write-only path if answer quotes the note
            if "text_missing_keywords" not in t5["failures"] and t5["chars"] >= 40:
                pass
            else:
                t5["failures"].append("missing_list_or_read_tool")
                t5["passed"] = False

    print("\n" + "=" * 72)
    print(f"E2E TOPIC-DRIFT RESULTS ({profile})")
    print("=" * 72)
    all_ok = True
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        if not r["passed"]:
            all_ok = False
        print(
            f"  [{mark}] {r['label']}: {r['elapsed_s']:.1f}s ttft={r['ttft_ms']} "
            f"band={r['slo_band']} route={r['route'] or '-'} tools={r['tool_names']} "
            f"fail={r['failures'] or []}"
        )

    report = {
        "thread_id": thread_id,
        "project_id": project_id,
        "profile": profile,
        "passed": all_ok,
        "turns": results,
        "summary": {
            "n": len(results),
            "passed": sum(1 for r in results if r["passed"]),
            "failed": sum(1 for r in results if not r["passed"]),
            "total_elapsed_s": round(sum(r["elapsed_s"] for r in results), 1),
            "slo_unacceptable": [
                r["label"] for r in results if r["slo_band"] == "unacceptable"
            ],
            "slo_degraded": [
                r["label"] for r in results if r["slo_band"] == "degraded"
            ],
            "failure_tags": sorted({f for r in results for f in r["failures"]}),
        },
    }
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved {out_path}")
    print(
        f"Summary: {report['summary']['passed']}/{report['summary']['n']} passed | "
        f"wall={report['summary']['total_elapsed_s']}s | "
        f"degraded={report['summary']['slo_degraded']} | "
        f"unacceptable={report['summary']['slo_unacceptable']}"
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except httpx.HTTPError as exc:
        print(f"[e2e] backend unreachable: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
