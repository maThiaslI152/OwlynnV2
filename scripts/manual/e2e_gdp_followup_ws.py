#!/usr/bin/env python3
"""Live WS E2E: capital trivia → GDP follow-up must use web_search (no tool_call leak).

Cache-busts T2 via a unique project_id + ``[eval-nonce=…]`` query suffix so a
healthy semantic-cache hit cannot soft-pass the routing assertion.

Run against a warm Owlynn backend:
  uv run python scripts/manual/e2e_gdp_followup_ws.py

Uses WebSocket ``idle`` as turn completion (not DOM polling).
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
import uuid
from typing import Any

import httpx
import websockets

API_URL = "http://127.0.0.1:8000"
TURN_TIMEOUT_S = 240
TOOL_LEAK_RE = re.compile(
    r"<\|?tool_call|GoogleSearch|<function=|</tool_call>", re.IGNORECASE
)


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


async def _run_turn(
    ws: Any,
    *,
    message: str,
    thread_id: str,
    label: str,
    project_id: str = "default",
) -> dict[str, Any]:
    """Send one user message; wait until status=idle. Return turn metrics."""
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
    router_meta: dict | None = None
    assistant = ""
    chunks: list[str] = []
    statuses: list[str] = []
    errors: list[str] = []
    idle = False
    ttft_ms: int | None = None

    while True:
        remaining = TURN_TIMEOUT_S - (time.monotonic() - since)
        if remaining <= 0:
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
            route = router_meta.get("route") if isinstance(router_meta, dict) else None
            print(
                f"  [router] route={route} meta_keys={list((router_meta or {}).keys())[:8]}"
            )
        elif etype == "tool_execution":
            name = (event.get("tool_name") or "").strip()
            st = event.get("status") or ""
            if name:
                tools.append(f"{name}:{st}")
            print(f"  [tool] {name} → {st}")
        elif etype == "chunk":
            part = event.get("content") or ""
            if part:
                if ttft_ms is None:
                    ttft_ms = int((time.monotonic() - since) * 1000)
                chunks.append(part)
        elif etype == "assistant.message":
            assistant = _assistant_text(event)
            print(f"  [assistant] {assistant[:180]!r}...")
        elif etype == "error":
            err = str(event.get("content") or event)
            errors.append(err)
            print(f"  [error] {err[:200]}")

    text = assistant or "".join(chunks)
    elapsed = time.monotonic() - since
    print(
        f"  done in {elapsed:.1f}s | ttft_ms={ttft_ms} | tools={tools} | chars={len(text)}"
    )
    return {
        "label": label,
        "elapsed_s": elapsed,
        "ttft_ms": ttft_ms,
        "idle": idle,
        "tools": tools,
        "tool_names": sorted({t.split(":")[0] for t in tools if t}),
        "router": router_meta,
        "text": text,
        "statuses": statuses,
        "errors": errors,
    }


def _route_from(meta: dict | None) -> str:
    if not isinstance(meta, dict):
        return ""
    return str(meta.get("route") or meta.get("final_route") or "")


async def main() -> int:
    health = httpx.get(f"{API_URL}/api/health", timeout=5.0)
    health.raise_for_status()
    print(f"[e2e] health={health.json()}")

    token = await _get_token()
    # Unique thread + project + query nonce so semantic cache cannot soft-pass T2.
    run_nonce = uuid.uuid4().hex[:12]
    thread_id = f"thread-e2e-gdp-{run_nonce}"
    project_id = f"e2e-gdp-{run_nonce}"
    ws_url = f"ws://127.0.0.1:8000/ws/chat/{thread_id}?token={token}"
    print(f"[e2e] thread={thread_id} project={project_id}")

    async with websockets.connect(ws_url, max_size=16 * 1024 * 1024) as ws:
        t1 = await _run_turn(
            ws,
            message="what is the capital city of Thailand",
            thread_id=thread_id,
            project_id=project_id,
            label="T1 capital (expect simple / Bangkok)",
        )
        # Unique suffix forces a cache miss; T2 must exercise live web_search.
        t2_msg = f"what is it's GDP? [eval-nonce={run_nonce}]"
        t2 = await _run_turn(
            ws,
            message=t2_msg,
            thread_id=thread_id,
            project_id=project_id,
            label="T2 GDP follow-up (expect web_search, no tool leak)",
        )

    # Detect silent cache replay (should be rare after nonce/project isolation)
    healthy_cache_hit = (
        not t2["tool_names"]
        and not _route_from(t2["router"])
        and not bool(TOOL_LEAK_RE.search(t2["text"] or ""))
        and len((t2["text"] or "").strip()) >= 40
    )
    poisoned_cache_suspected = (
        not t2["tool_names"]
        and not _route_from(t2["router"])
        and bool(TOOL_LEAK_RE.search(t2["text"] or ""))
        and t2["elapsed_s"] < 20
    )
    if poisoned_cache_suspected:
        print(
            "\n[e2e] WARNING: T2 looks like a poisoned semantic-cache replay "
            "(no tools/router + tool leak). Re-run after purge if this fails."
        )
    elif healthy_cache_hit:
        print(
            "\n[e2e] FAIL HINT: T2 looks like a healthy semantic-cache hit despite "
            "cache-bust nonce — routing path was not exercised."
        )

    checks: list[tuple[str, bool, str]] = []

    # Turn 1
    checks.append(("T1 idle", t1["idle"], ""))
    checks.append(
        (
            "T1 no tool_call leak",
            not bool(TOOL_LEAK_RE.search(t1["text"] or "")),
            (t1["text"] or "")[:120],
        )
    )
    checks.append(
        (
            "T1 mentions Bangkok",
            "bangkok" in (t1["text"] or "").lower(),
            (t1["text"] or "")[:120],
        )
    )

    # Turn 2 — must hit live web_search (cache soft-pass is not allowed)
    checks.append(("T2 idle", t2["idle"], ""))
    t2_used_search = "web_search" in t2["tool_names"]
    checks.append(
        (
            "T2 used web_search",
            t2_used_search,
            f"tools={t2['tool_names']} router={_route_from(t2['router'])} "
            f"cache_hit={healthy_cache_hit}",
        )
    )
    checks.append(
        (
            "T2 no tool_call leak",
            not bool(TOOL_LEAK_RE.search(t2["text"] or "")),
            (t2["text"] or "")[:200],
        )
    )
    checks.append(
        (
            "T2 not empty answer",
            len((t2["text"] or "").strip()) >= 40,
            f"chars={len(t2['text'] or '')}",
        )
    )
    t2_lower = (t2["text"] or "").lower()
    checks.append(
        (
            "T2 GDP-related answer",
            any(
                k in t2_lower for k in ("gdp", "billion", "baht", "economy", "economic")
            ),
            (t2["text"] or "")[:200],
        )
    )
    # Must not stay on simple for this follow-up (skip when cache skipped the graph)
    route2 = _route_from(t2["router"])
    if route2:
        checks.append(
            (
                "T2 route not simple",
                not route2.startswith("simple"),
                f"route={route2}",
            )
        )

    print("\n" + "=" * 64)
    print("E2E GDP FOLLOW-UP RESULTS")
    print("=" * 64)
    all_ok = True
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        extra = f" — {detail}" if detail and not ok else ""
        print(f"  [{mark}] {name}{extra}")

    out = {
        "thread_id": thread_id,
        "project_id": project_id,
        "run_nonce": run_nonce,
        "passed": all_ok,
        "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks],
        "t1": {k: v for k, v in t1.items() if k != "router"},
        "t2": {
            **{k: v for k, v in t2.items() if k != "router"},
            "route": route2,
            "router": t2.get("router"),
            "cache_busted": True,
            "healthy_cache_hit": healthy_cache_hit,
        },
    }
    out_path = "/tmp/e2e_gdp_followup_result.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nSaved {out_path}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130)
