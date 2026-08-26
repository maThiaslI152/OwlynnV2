#!/usr/bin/env python3
"""Playwright UI E2E: same-thread topic drift + semantic cache MISS/HIT.

Usable Normal-mode gate for multi-turn chat latency on the real UI.
Completion source of truth: WebSocket ``status: idle`` (via frontier helpers).

Profiles:
  usable — T1 miss → T1r hit → T2 web → T4 write
  full   — usable + T3 weather + T5 list/read + T6 GDP return

  PYTHONPATH=. uv run python scripts/manual/e2e_topic_drift_ui.py --profile usable
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from playwright.async_api import async_playwright

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_URL = os.getenv("OWLYNN_EVAL_BASE_URL", "http://127.0.0.1:5173")
API_URL = os.getenv("OWLYNN_EVAL_API_URL", "http://127.0.0.1:8000")
SCREENSHOT_DIR = REPO_ROOT / "assets" / "topic_drift_ui_screenshots"
DEFAULT_OUT = Path("/tmp/e2e_topic_drift_ui_result.json")
CACHE_STORE_WAIT_S = 2.0
TOOL_LEAK_RE = re.compile(
    r"<\|?tool_call|GoogleSearch|<function=|</tool_call>", re.IGNORECASE
)

# SLO bands from docs/PERFORMANCE_SLOS.md (warm local_only)
SLO = {
    "cache_ttft_ok_ms": 100,
    "cache_ttft_degraded_ms": 500,
    "simple_turn_s": 3.0,
    "simple_unacceptable_s": 8.0,
    "web_turn_s": 8.0,
    "web_unacceptable_s": 25.0,
    "complex_turn_s": 20.0,
    "complex_unacceptable_s": 60.0,
}


def _load_frontier():
    path = REPO_ROOT / "scripts" / "run_local_frontier_eval.py"
    spec = importlib.util.spec_from_file_location("frontier_eval", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load run_local_frontier_eval.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["frontier_eval"] = mod
    spec.loader.exec_module(mod)
    return mod


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--profile",
        choices=("full", "usable"),
        default="usable",
        help="usable=MISS/HIT+web+write; full=6-turn topic drift + cache pair",
    )
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="JSON report path")
    p.add_argument(
        "--headed",
        action="store_true",
        help="Show browser window (default headless)",
    )
    return p.parse_args(argv)


def _cache_model_since(ws_log: Any, since_ts: float) -> bool:
    for ev in ws_log.events:
        if ev["ts"] < since_ts:
            continue
        if ev["type"] not in ("chunk", "assistant.message"):
            continue
        payload = ev.get("payload") or {}
        if payload.get("model") == "cache":
            return True
    return False


def _tool_durations_since(ws_log: Any, since_ts: float) -> dict[str, float]:
    started: dict[str, float] = {}
    durations: dict[str, float] = {}
    for ev in ws_log.events:
        if ev["type"] != "tool_execution" or ev["ts"] < since_ts:
            continue
        payload = ev.get("payload") or {}
        name = (payload.get("tool_name") or "").strip()
        if not name:
            continue
        st = payload.get("status")
        if st == "running":
            started[name] = ev["ts"]
        elif st in ("success", "error") and name in started:
            durations[name] = ev["ts"] - started[name]
            dur = payload.get("duration")
            if isinstance(dur, (int, float)):
                durations[name] = float(dur)
    return durations


def _tool_success_count(ws_log: Any, since_ts: float, tool_name: str) -> int:
    n = 0
    for ev in ws_log.events:
        if ev["type"] != "tool_execution" or ev["ts"] < since_ts:
            continue
        payload = ev.get("payload") or {}
        if (payload.get("tool_name") or "").strip() != tool_name:
            continue
        if payload.get("status") == "success":
            n += 1
    return n


def _slo_band(kind: str, elapsed_s: float, ttft_ms: float | None) -> str:
    if kind == "cache":
        if ttft_ms is None:
            return "unacceptable"
        if ttft_ms <= SLO["cache_ttft_ok_ms"]:
            return "ok"
        if ttft_ms <= SLO["cache_ttft_degraded_ms"]:
            return "degraded"
        return "unacceptable"
    if kind == "simple":
        if elapsed_s > SLO["simple_unacceptable_s"]:
            return "unacceptable"
        if elapsed_s > SLO["simple_turn_s"]:
            return "degraded"
        return "ok"
    if kind == "web":
        if elapsed_s > SLO["web_unacceptable_s"]:
            return "unacceptable"
        if elapsed_s > SLO["web_turn_s"]:
            return "degraded"
        return "ok"
    if elapsed_s > SLO["complex_unacceptable_s"]:
        return "unacceptable"
    if elapsed_s > SLO["complex_turn_s"]:
        return "degraded"
    return "ok"


def _build_turns(run_nonce: str, note_name: str) -> list[dict[str, Any]]:
    capital = "what is the capital city of Thailand"
    return [
        {
            "id": "T1",
            "label": "T1 capital cache MISS",
            "prompt": capital,
            "kind": "simple",
            "expect_cache": "miss",
            "min_chars": 5,
            "text_any": ["bangkok"],
            "forbid_tools": ["web_search"],
            "require_router": True,
            "timeout_s": 120,
            "post_wait_s": CACHE_STORE_WAIT_S,
        },
        {
            "id": "T1r",
            "label": "T1r capital cache HIT",
            "prompt": capital,
            "kind": "cache",
            "expect_cache": "hit",
            "min_chars": 5,
            "text_any": ["bangkok"],
            "forbid_tools": ["web_search"],
            "require_router": False,
            "timeout_s": 60,
        },
        {
            "id": "T2",
            "label": "T2 GDP follow-up web MISS",
            "prompt": f"what is it's GDP roughly? [eval-nonce={run_nonce}]",
            "kind": "web",
            "expect_cache": "miss",
            "min_chars": 40,
            "must_tools": ["web_search"],
            "text_any": ["gdp", "billion", "economy", "baht", "dollar"],
            "timeout_s": 180,
        },
        {
            "id": "T3",
            "label": "T3 weather digression web MISS",
            "prompt": (
                f"anyway what's the weather in Bangkok right now? "
                f"[eval-nonce={run_nonce}-wx]"
            ),
            "kind": "web",
            "expect_cache": "miss",
            "min_chars": 30,
            "must_tools": ["web_search"],
            "text_any": ["c", "°", "temp", "rain", "humid", "weather", "bangkok"],
            "timeout_s": 180,
        },
        {
            "id": "T4",
            "label": "T4 write workspace note MISS",
            "prompt": (
                f"Save a short note to my workspace as {note_name} summarizing "
                f"Bangkok capital + that we asked about GDP and weather. "
                f"Use write_workspace_file. Keep it under 80 words. "
                f"[eval-nonce={run_nonce}-write]"
            ),
            "kind": "complex",
            "expect_cache": "miss",
            "min_chars": 0,
            "must_tools": ["write_workspace_file"],
            "timeout_s": 180,
        },
        {
            "id": "T5",
            "label": "T5 list/read note MISS",
            "prompt": (
                f"List workspace files and read {note_name} back to me. "
                f"[eval-nonce={run_nonce}-read]"
            ),
            "kind": "complex",
            "expect_cache": "miss",
            "min_chars": 20,
            "must_tools": [],
            "text_any": [
                "bangkok",
                note_name.replace(".txt", ""),
                "gdp",
                "weather",
            ],
            "soft_file_tools": True,
            "timeout_s": 180,
        },
        {
            "id": "T6",
            "label": "T6 back to GDP web MISS",
            "prompt": (
                f"ok back to economics — is Thailand's GDP growing this year? "
                f"[eval-nonce={run_nonce}-gdp2]"
            ),
            "kind": "web",
            "expect_cache": "miss",
            "min_chars": 40,
            "must_tools": ["web_search"],
            "text_any": ["gdp", "growth", "percent", "%", "economy", "forecast"],
            "timeout_s": 180,
        },
    ]


async def _wait_backend(timeout_s: float = 90.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{API_URL}/api/health")
                if resp.status_code == 200 and resp.json().get("agent") == "ready":
                    return True
        except Exception:
            pass
        await asyncio.sleep(1.0)
    return False


async def _wait_ui(timeout_s: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(BASE_URL)
                if resp.status_code == 200:
                    return True
        except Exception:
            pass
        await asyncio.sleep(1.0)
    return False


async def _run_turn(
    *,
    fe: Any,
    page: Any,
    ws_log: Any,
    item: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    print("\n" + "─" * 72)
    print(f"  {item['label']}")
    print(f"  USER: {item['prompt']}")
    print("─" * 72)

    turn_wall = time.time()
    start = time.monotonic()
    # Wait until composer is editable (disabled while graph busy / reconnecting).
    try:
        await page.locator("textarea:not([disabled])").wait_for(
            state="visible", timeout=60000
        )
    except Exception as exc:
        print(f"  [warn] textarea not enabled: {exc}")
    await fe.send_message(page, item["prompt"])
    wait_result = await fe.wait_for_turn_complete(
        page,
        timeout_s=int(item.get("timeout_s", 180)),
        min_chars=int(item.get("min_chars", 5)),
        expected_tools=item.get("must_tools") or None,
        ws_log=ws_log,
        since_ts=turn_wall,
    )
    elapsed = time.monotonic() - start

    text = (
        wait_result.get("response_text")
        or ws_log.assistant_text_since(turn_wall)
        or ws_log.chunk_text_since(turn_wall)
        or ""
    )
    tools = wait_result.get("executed_tools_ws") or ws_log.tools_since(turn_wall)
    tool_names = sorted(set(tools))
    ttft_ms = ws_log.first_chunk_ttft_ms(turn_wall)
    router = ws_log.router_meta_since(turn_wall)
    route = str(router.get("route") or "")
    cache_hit = _cache_model_since(ws_log, turn_wall)
    idle = bool(wait_result.get("graph_idle")) or ws_log.idle_since(turn_wall)
    leak = bool(TOOL_LEAK_RE.search(text or ""))
    tool_durations = _tool_durations_since(ws_log, turn_wall)

    expect_cache = item.get("expect_cache", "miss")
    if cache_hit:
        cache_outcome = "hit"
    else:
        cache_outcome = "miss"

    failures: list[str] = []
    if not wait_result.get("completed") or not idle:
        failures.append("no_idle")
    if leak:
        failures.append("tool_leak")
    if expect_cache == "hit" and not cache_hit:
        failures.append("expected_cache_hit")
    if expect_cache == "miss" and cache_hit:
        failures.append("unexpected_cache_hit")
    if item.get("require_router") and expect_cache == "miss" and not router:
        failures.append("missing_router_info")
    if expect_cache == "hit" and router:
        failures.append("cache_hit_had_router")
    if expect_cache == "hit" and tool_names:
        failures.append(f"cache_hit_had_tools:{tool_names}")

    min_chars = int(item.get("min_chars") or 0)
    if min_chars and len((text or "").strip()) < min_chars:
        failures.append("short_answer")

    for t in item.get("must_tools") or []:
        if t not in tool_names:
            failures.append(f"missing_tool:{t}")
    for t in item.get("forbid_tools") or []:
        if t in tool_names:
            failures.append(f"unexpected_tool:{t}")

    must_substrings = item.get("text_any") or []
    if must_substrings:
        lower = (text or "").lower()
        if not any(s.lower() in lower for s in must_substrings):
            failures.append("text_missing_keywords")

    if item.get("soft_file_tools"):
        names = set(tool_names)
        file_ok = bool(
            names.intersection(
                {
                    "list_workspace_files",
                    "read_workspace_file",
                    "list_workspace",
                    "read_file",
                }
            )
        )
        if not file_ok and (
            "text_missing_keywords" in failures or len((text or "").strip()) < 40
        ):
            failures.append("missing_list_or_read_tool")

    band = _slo_band(
        item["kind"], elapsed, ttft_ms if isinstance(ttft_ms, (int, float)) else None
    )
    write_count = _tool_success_count(ws_log, turn_wall, "write_workspace_file")
    if item["id"] == "T4" and write_count > 1:
        failures.append(f"write_thrash:{write_count}")

    shot = SCREENSHOT_DIR / f"{index:02d}_{item['id']}.png"
    try:
        await page.screenshot(path=str(shot))
    except Exception as exc:
        print(f"  [warn] screenshot failed: {exc}")

    post_wait = float(item.get("post_wait_s") or 0)
    if post_wait > 0:
        print(f"  [cache] waiting {post_wait:.1f}s for semantic store...")
        await asyncio.sleep(post_wait)

    print(
        f"  done in {elapsed:.1f}s | ttft_ms={ttft_ms} | cache={cache_outcome} | "
        f"route={route or '-'} | tools={tool_names} | band={band} | "
        f"fail={failures or 'none'}"
    )

    return {
        "id": item["id"],
        "label": item["label"],
        "prompt": item["prompt"],
        "kind": item["kind"],
        "elapsed_s": round(elapsed, 2),
        "ttft_ms": ttft_ms,
        "idle": idle,
        "completed": bool(wait_result.get("completed")),
        "tools": tools,
        "tool_names": tool_names,
        "tool_durations_s": {k: round(v, 2) for k, v in tool_durations.items()},
        "write_count": write_count if item["id"] == "T4" else None,
        "route": route,
        "router": router,
        "cache_outcome": cache_outcome,
        "expect_cache": expect_cache,
        "text": text,
        "text_preview": (text or "")[:300],
        "chars": len(text or ""),
        "tool_leak": leak,
        "slo_band": band,
        "failures": failures,
        "passed": not failures,
        "screenshot": str(shot),
    }


async def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    fe = _load_frontier()
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[e2e-ui] waiting for backend {API_URL}...")
    if not await _wait_backend():
        print("[e2e-ui] FAIL: backend not ready (agent!=ready)")
        return 2
    print(f"[e2e-ui] waiting for UI {BASE_URL}...")
    if not await _wait_ui():
        print("[e2e-ui] FAIL: UI not reachable")
        return 2

    await fe.ensure_run_token()
    prior = await fe.fetch_runtime_profile()
    prior_scope = prior.get("scope_clarification_enabled")
    prior_plan = prior.get("plan_review_enabled")
    prior_execution = prior.get("execution_policy", "auto_approve")

    print("[e2e-ui] settings: local_only + auto_approve + HITL off")
    await fe.set_unified_settings(
        cloud_routing_mode="local_only",
        scope_clarification_enabled=False,
        plan_review_enabled=False,
        execution_policy="auto_approve",
    )

    run_nonce = uuid.uuid4().hex[:10]
    note_name = f"bangkok_notes_{run_nonce}.txt"
    project_name = f"TopicDriftUI_{run_nonce}"
    project_id = await fe.create_project(project_name)
    turns = _build_turns(run_nonce, note_name)
    if args.profile == "usable":
        # T1 miss, T1r hit, T2 web, T4 write
        keep = {"T1", "T1r", "T2", "T4"}
        turns = [t for t in turns if t["id"] in keep]

    report: dict[str, Any] = {
        "profile": args.profile,
        "project_id": project_id,
        "project_name": project_name,
        "run_nonce": run_nonce,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "base_url": BASE_URL,
        "api_url": API_URL,
        "turns": [],
    }

    exit_code = 0
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=not args.headed)
            context = await browser.new_context(
                viewport={"width": 1440, "height": 900}
            )
            page = await context.new_page()
            ws_log = fe.WsEventLog()
            ws_log.attach(page)

            await page.goto(
                f"{BASE_URL}?project_id={project_id}",
                wait_until="load",
            )
            await fe.wait_for_ready(page)
            await page.wait_for_timeout(1500)
            await fe.wait_for_ready(page)

            for index, item in enumerate(turns):
                result = await _run_turn(
                    fe=fe,
                    page=page,
                    ws_log=ws_log,
                    item=item,
                    index=index,
                )
                report["turns"].append(result)

            await browser.close()
    finally:
        try:
            await fe.set_unified_settings(
                scope_clarification_enabled=prior_scope,
                plan_review_enabled=prior_plan,
                execution_policy=prior_execution,
            )
        except Exception as exc:
            print(f"[e2e-ui] warn: restore settings failed: {exc}")

    passed = sum(1 for t in report["turns"] if t["passed"])
    total = len(report["turns"])
    unacceptable = [t for t in report["turns"] if t["slo_band"] == "unacceptable"]
    functional_fail = [t for t in report["turns"] if not t["passed"]]
    report["passed_count"] = passed
    report["total"] = total
    report["all_passed"] = passed == total and total > 0
    report["any_unacceptable"] = bool(unacceptable)
    report["usable_gate"] = report["all_passed"] and not report["any_unacceptable"]

    print("\n" + "=" * 72)
    print(f"E2E TOPIC-DRIFT UI RESULTS ({args.profile})")
    print("=" * 72)
    for t in report["turns"]:
        status = "PASS" if t["passed"] else "FAIL"
        print(
            f"  [{status}] {t['id']:4} {t['elapsed_s']:6.1f}s  "
            f"ttft={t['ttft_ms']!s:>8}  cache={t['cache_outcome']:4}  "
            f"band={t['slo_band']:12}  tools={t['tool_names']}  "
            f"fail={t['failures'] or '-'}"
        )
    print("-" * 72)
    print(
        f"  functional {passed}/{total}  "
        f"unacceptable={len(unacceptable)}  "
        f"usable_gate={report['usable_gate']}"
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"  report → {args.out}")

    if functional_fail or unacceptable:
        exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
