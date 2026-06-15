#!/usr/bin/env python3
"""
Educator evaluation for Owlynn — UID10667 PDF study session (EDU1–EDU8).

Usage:
  python scripts/prepare_uid10667_fixtures.py
  python scripts/run_educator_eval.py --profile auto
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from playwright.async_api import Page, async_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
FIXTURE_DIR = REPO_ROOT / "assets" / "eval_fixtures" / "uid10667"
SCREENSHOT_DIR = REPO_ROOT / "assets" / "educator_eval_screenshots"
OUTPUT_DATA = REPO_ROOT / "data" / "educator_eval_run_data.json"
REPORT_DIR = REPO_ROOT / "docs" / "evaluations"

CHAPTER1 = "uid10667/chapter1-digital-literacy.pdf"
COMPLEX_TIMEOUT_S = 900


def _load_frontier():
    path = REPO_ROOT / "scripts" / "run_local_frontier_eval.py"
    spec = importlib.util.spec_from_file_location("frontier_eval", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load run_local_frontier_eval.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["frontier_eval"] = mod
    spec.loader.exec_module(mod)
    return mod


fe = _load_frontier()


def load_keywords() -> dict[str, Any]:
    path = FIXTURE_DIR / "keywords.json"
    if not path.exists():
        return {
            "chapters": {Path(CHAPTER1).name: ["Digital Literacy", "UID10667"]},
            "criticism_prompt_keyword": "Digital Literacy",
        }
    return json.loads(path.read_text(encoding="utf-8"))


def build_prompts(meta: dict[str, Any]) -> list[dict[str, Any]]:
    kw = meta.get("criticism_prompt_keyword", "Digital Literacy")
    ch1_keys = meta.get("chapters", {}).get("chapter1-digital-literacy.pdf", [])
    keyword_hint = ch1_keys[0] if ch1_keys else kw
    return [
        {
            "id": "EDU1",
            "topic": "PDF Study Guide",
            "new_chat_before": True,
            "response_style": "learning",
            "attach_file": CHAPTER1,
            "check_processed": True,
            "prompt": ("Help me study this PDF. Explain the main ideas for exam prep."),
            "expected_route": "complex",
            "expected_tools_any": ["read_workspace_file"],
            "forbid_tools": ["web_search"],
            "educator_keywords": ch1_keys[:8],
            "min_keyword_hits": 2,
            "timeout_s": COMPLEX_TIMEOUT_S,
            "min_response_chars": 200,
            "pipeline_notes": "attach PDF → read_workspace_file → learning-mode study guide",
        },
        {
            "id": "EDU2",
            "topic": "Quiz From Chapter",
            "response_style": "learning",
            "prompt": "Quiz me on 3 concepts from that chapter.",
            "expected_route": "complex",
            "educator_keywords": ch1_keys[:8] + ["question", "quiz"],
            "min_keyword_hits": 1,
            "timeout_s": COMPLEX_TIMEOUT_S,
            "min_response_chars": 80,
            "pipeline_notes": "same thread — quiz without re-read",
        },
        {
            "id": "EDU3",
            "topic": "User Criticism Adaptation",
            "response_style": "learning",
            "prompt": (
                f"Your explanation of {keyword_hint} was wrong — the PDF emphasizes "
                "online learning guidelines and digital competency. Please correct your answer."
            ),
            "expected_route": "complex",
            "correction_phrases": [
                "you're right",
                "you are right",
                "correction",
                "actually",
                "clarify",
                "apolog",
                "revise",
                "correct",
            ],
            "timeout_s": COMPLEX_TIMEOUT_S,
            "min_response_chars": 100,
            "pipeline_notes": "criticism → acknowledge and revise",
        },
        {
            "id": "EDU4",
            "topic": "Self-Reinforcement Acknowledgment",
            "response_style": "learning",
            "prompt": f"I finally understand {keyword_hint} now.",
            "expected_route": "complex",
            "ack_phrases": [
                "great",
                "glad",
                "good",
                "understand",
                "excellent",
                "nice",
                "well done",
                "makes sense",
            ],
            "timeout_s": COMPLEX_TIMEOUT_S,
            "min_response_chars": 50,
            "informational_only": True,
            "pipeline_notes": "self-reinforcement acknowledgment (informational)",
        },
        {
            "id": "EDU5",
            "topic": "Cross-Thread Struggle Recall",
            "new_chat_before": True,
            "response_style": "learning",
            "prompt": "What did I struggle with in Digital Literacy?",
            "expected_route": "complex",
            "educator_keywords_topic": [keyword_hint, "digital literacy"],
            "educator_keywords_substantive": [
                "wrong",
                "corrected",
                "misconception",
                "online learning",
                "competency",
                "guidelines",
                "emphasiz",
                "criticism",
                "confus",
            ],
            "min_topic_hits": 1,
            "min_substantive_hits": 1,
            "forbid_phrases": [
                "don't have a record",
                "do not have a record",
                "no specific record",
                "don't have a specific",
                "cannot recall what you struggled",
                "can't recall what you struggled",
            ],
            "timeout_s": COMPLEX_TIMEOUT_S,
            "min_response_chars": 20,
            "pipeline_notes": "new thread — recall study misconception atoms from LTM",
        },
        {
            "id": "EDU6",
            "topic": "Flashcard Deck From Chapter",
            "response_style": "learning",
            "prompt": (
                "Make flashcards from that chapter — at least 5 term/definition pairs "
                "for exam review."
            ),
            "expected_route": "complex",
            "expected_tools_any": ["flashcard_deck_create", "read_workspace_file"],
            "educator_keywords": [
                "flashcard",
                "front",
                "back",
                "definition",
                keyword_hint,
            ],
            "min_keyword_hits": 2,
            "timeout_s": COMPLEX_TIMEOUT_S,
            "min_response_chars": 80,
            "pipeline_notes": "flashcard deck creation from same thread PDF context",
        },
        {
            "id": "EDU7",
            "topic": "Mock Exam Weak Areas",
            "response_style": "learning",
            "prompt": "Give me a short mock exam (3 questions) and highlight my weak areas.",
            "expected_route": "complex",
            "educator_keywords": ["question", "weak", keyword_hint],
            "min_keyword_hits": 2,
            "timeout_s": COMPLEX_TIMEOUT_S,
            "min_response_chars": 100,
            "pipeline_notes": "mock exam + weak-area summary",
        },
        {
            "id": "EDU8",
            "topic": "Interactive Inline Widget",
            "response_style": "learning",
            "prompt": (
                "Walk me through the main ideas step by step, then give me one "
                "multiple-choice question to check my understanding."
            ),
            "expected_route": "complex",
            "require_interactive_fence": True,
            "interactive_fence_any": ["owlynn-steps", "owlynn-quiz"],
            "educator_keywords": [keyword_hint],
            "min_keyword_hits": 1,
            "timeout_s": COMPLEX_TIMEOUT_S,
            "min_response_chars": 80,
            "pipeline_notes": "inline owlynn-steps or owlynn-quiz fence in reply",
        },
    ]


async def set_eval_response_style(page: Page, style: str | None) -> None:
    if not style:
        return
    await page.evaluate(
        """(style) => {
          if (window.__owlynnEval?.setResponseStyle) {
            window.__owlynnEval.setResponseStyle(style);
          }
        }""",
        style,
    )


async def send_eval_message(
    page: Page, text: str, *, response_style: str | None
) -> None:
    await set_eval_response_style(page, response_style)
    await fe.send_message(page, text)


def _keyword_hits(body: str, keywords: list[str]) -> list[str]:
    lower = body.lower()
    return [k for k in keywords if k.lower() in lower]


def score_educator_exchange(exchange: dict, expected: dict, *, profile: str) -> dict:
    scores = fe.score_exchange(exchange, expected, profile=profile)

    body = fe._normalize_response(exchange.get("assistant_response_full", ""))
    executed = exchange.get("executed_tools") or []
    forbid_phrase_fail = False

    forbid = expected.get("forbid_tools") or []
    forbidden_used = [t for t in forbid if t in executed]
    scores["forbid_tools_ok"] = not forbidden_used
    if forbidden_used:
        scores["forbidden_tools_used"] = forbidden_used
        scores["grade"] = max(0, scores["grade"] - 20)

    any_tools = expected.get("expected_tools_any")
    if any_tools:
        scores["tools_any_ok"] = any(t in executed for t in any_tools)
        if scores["tools_any_ok"] and not scores.get("tools_match"):
            scores["grade"] = min(100, scores["grade"] + 15)

    edu_kw = expected.get("educator_keywords") or []
    min_hits = int(expected.get("min_keyword_hits", 0))
    if edu_kw and min_hits:
        hits = _keyword_hits(body, edu_kw)
        scores["keyword_hits"] = hits
        scores["keywords_ok"] = len(hits) >= min_hits
        if scores["keywords_ok"]:
            scores["grade"] = min(100, scores["grade"] + 10)
        else:
            scores["grade"] = max(0, scores["grade"] - 10)

    topic_kw = expected.get("educator_keywords_topic") or []
    substantive_kw = expected.get("educator_keywords_substantive") or []
    min_topic = int(expected.get("min_topic_hits", 0))
    min_substantive = int(expected.get("min_substantive_hits", 0))
    if topic_kw and substantive_kw and (min_topic or min_substantive):
        topic_hits = _keyword_hits(body, topic_kw)
        substantive_hits = _keyword_hits(body, substantive_kw)
        scores["topic_hits"] = topic_hits
        scores["substantive_hits"] = substantive_hits
        scores["recall_substantive_ok"] = len(substantive_hits) >= max(
            min_substantive, 1
        )
        scores["recall_topic_ok"] = len(topic_hits) >= max(min_topic, 1)
        scores["keywords_ok"] = (
            scores["recall_substantive_ok"] and scores["recall_topic_ok"]
        )
        scores["keyword_hits"] = topic_hits + substantive_hits
        if scores["keywords_ok"]:
            scores["grade"] = min(100, scores["grade"] + 10)
        else:
            scores["grade"] = max(0, scores["grade"] - 20)

    forbid_phrases = expected.get("forbid_phrases") or []
    if forbid_phrases:
        denied = [p for p in forbid_phrases if p in body.lower()]
        scores["forbid_phrases_ok"] = not denied
        if denied:
            scores["forbidden_phrases"] = denied
            scores["grade"] = max(0, scores["grade"] - 30)
            forbid_phrase_fail = True

    corr = expected.get("correction_phrases") or []
    if corr:
        scores["correction_ok"] = any(p in body.lower() for p in corr)
        if scores["correction_ok"]:
            scores["grade"] = min(100, scores["grade"] + 10)
        else:
            scores["grade"] = max(0, scores["grade"] - 15)

    ack = expected.get("ack_phrases") or []
    if ack:
        scores["ack_ok"] = any(p in body.lower() for p in ack)
        if scores["ack_ok"]:
            scores["grade"] = min(100, scores["grade"] + 5)

    if expected.get("baseline_expected_fail"):
        scores["baseline_gap_documented"] = not scores.get("recall_ok", False)
        if not scores.get("recall_ok"):
            scores["grade"] = min(scores["grade"], 40)

    if expected.get("informational_only"):
        scores["informational"] = True

    fence_any = expected.get("interactive_fence_any") or []
    if expected.get("require_interactive_fence") and fence_any:
        found = [f for f in fence_any if f"```{f}" in body]
        scores["interactive_fence_hits"] = found
        scores["interactive_fence_ok"] = bool(found)
        if scores["interactive_fence_ok"]:
            scores["grade"] = min(100, scores["grade"] + 10)
        else:
            scores["grade"] = max(0, scores["grade"] - 25)

    scores["grade"] = min(100, max(0, scores["grade"]))
    scores["pass"] = (
        scores["grade"] >= 70 and not forbidden_used and not forbid_phrase_fail
    )
    if edu_kw and min_hits:
        scores["pass"] = scores["pass"] and scores.get("keywords_ok", False)
    if topic_kw and substantive_kw and (min_topic or min_substantive):
        scores["pass"] = scores["pass"] and scores.get("keywords_ok", False)
        scores["pass"] = scores["pass"] and scores.get("forbid_phrases_ok", True)
    if expected.get("require_interactive_fence"):
        scores["pass"] = scores["pass"] and scores.get("interactive_fence_ok", False)
    if expected.get("baseline_expected_fail"):
        scores["pass"] = bool(scores.get("baseline_gap_documented"))
    return scores


async def run_edu_turn(
    page: Page,
    item: dict,
    *,
    profile: str,
    project_id: str,
    ws_log: fe.WsEventLog,
    index: int,
) -> dict:
    from src.agent.cloud_circuit_breaker import reset_circuit_breaker

    reset_circuit_breaker()
    turn_start = time.time()

    if item.get("new_chat_before"):
        await fe.new_chat(page)

    attach_name = item.get("attach_file")
    if attach_name:
        fixture = fe.FIXTURE_DIR / attach_name
        if not fixture.exists():
            raise FileNotFoundError(f"Missing fixture: {fixture}")
        await fe.attach_file_via_drop(page, fixture)
        if item.get("check_processed"):
            processed = await fe.poll_file_processed(
                project_id, Path(attach_name).name, timeout_s=45.0
            )
            item = {**item, "_upload_processed": processed}

    style = item.get("response_style")
    await send_eval_message(page, item["prompt"], response_style=style)

    wait_result = await fe.wait_for_turn_complete(
        page,
        timeout_s=item.get("timeout_s", COMPLEX_TIMEOUT_S),
        min_chars=item.get("min_response_chars", 10),
        expected_tools=item.get("expected_tools"),
        ws_log=ws_log,
        since_ts=turn_start,
    )
    duration = time.monotonic() - turn_start
    orch = await fe.get_orchestration_data(page)
    model_tier = await fe.fetch_last_turn_tier()
    ws_tools = wait_result.get("executed_tools_ws") or ws_log.tools_since(turn_start)
    ws_router = ws_log.router_meta_since(turn_start)
    response_text = wait_result["response_text"]

    exchange = {
        "turn_index": index + 1,
        "prompt_id": item["id"],
        "topic": item["topic"],
        "pipeline_notes": item.get("pipeline_notes", ""),
        "user_query": item["prompt"],
        "assistant_response": response_text[:500]
        + ("..." if len(response_text) > 500 else ""),
        "assistant_response_full": response_text,
        "response_completed": wait_result["completed"],
        "route": ws_router.get("route") or orch.get("route"),
        "executed_tools": ws_tools or wait_result["executed_tools"],
        "model_tier": model_tier,
        "duration_seconds": round(duration, 2),
        "file_processed": item.get("_upload_processed", False),
        "status": "scored",
    }
    return exchange


def write_report(eval_data: dict, scores_by_id: dict[str, dict]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    path = REPORT_DIR / f"educator-eval-{today}.md"
    lines = [
        "---",
        "status: active",
        "category: evaluation",
        "audience: agent",
        f"last_updated: {today}",
        "---",
        "",
        f"# Educator Eval — {today}",
        "",
        f"Profile: **{eval_data.get('runtime_profile')}** | Project: `{eval_data.get('project_id')}`",
        "",
        "## Summary",
        "",
        "| Turn | Grade | Pass | Notes |",
        "|------|-------|------|-------|",
    ]
    for ex in eval_data.get("exchanges", []):
        pid = ex["prompt_id"]
        sc = scores_by_id.get(pid, {})
        lines.append(
            f"| {pid} | {sc.get('grade', 0)} | {sc.get('pass', False)} | "
            f"{ex.get('topic', '')} |"
        )
    lines.extend(["", "## Turn details", ""])
    for ex in eval_data.get("exchanges", []):
        pid = ex["prompt_id"]
        sc = scores_by_id.get(pid, {})
        lines.append(f"### {pid} — {ex.get('topic')}")
        lines.append(f"- Grade: {sc.get('grade')} | Pass: {sc.get('pass')}")
        lines.append(
            f"- Route: `{ex.get('route')}` | Tools: `{ex.get('executed_tools')}`"
        )
        if sc.get("keyword_hits"):
            lines.append(f"- Keyword hits: {sc['keyword_hits']}")
        lines.append(f"- Response excerpt: {ex.get('assistant_response', '')[:300]}")
        shot = ex.get("screenshot")
        if shot:
            lines.append(f"- Screenshot: `{shot}`")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


async def main() -> None:
    parser = argparse.ArgumentParser(description="Owlynn educator evaluation")
    parser.add_argument(
        "--profile",
        choices=("auto", "local", "cloud"),
        default="auto",
    )
    parser.add_argument("--cloud-off", action="store_true")
    args = parser.parse_args()

    fixture_script = REPO_ROOT / "scripts" / "prepare_uid10667_fixtures.py"
    ch1 = FIXTURE_DIR / "chapter1-digital-literacy.pdf"
    if not ch1.exists():
        import subprocess

        subprocess.run([sys.executable, str(fixture_script)], check=True)

    meta = load_keywords()
    prompts = build_prompts(meta)

    runtime = await fe.fetch_runtime_profile()
    if args.cloud_off:
        await fe.set_unified_settings(cloud_escalation_enabled=False)
        runtime = await fe.fetch_runtime_profile()
    profile = runtime["effective_profile"] if args.profile == "auto" else args.profile

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    project_id = await fe.create_project(f"EducatorEval_{uuid.uuid4().hex[:6]}")

    eval_data: dict[str, Any] = {
        "project_id": project_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "runtime_profile": profile,
        "exchanges": [],
        "scores": {},
    }
    scores_by_id: dict[str, dict] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await (
            await browser.new_context(viewport={"width": 1440, "height": 900})
        ).new_page()
        ws_log = fe.WsEventLog()
        ws_log.attach(page)

        await page.goto(
            f"{fe.BASE_URL}/?project={project_id}", wait_until="networkidle"
        )
        await asyncio.sleep(2.0)

        for idx, item in enumerate(prompts):
            print(f"\n[EDU] === {item['id']}: {item['topic']} ===")
            if item.get("id") == "EDU5":
                await asyncio.sleep(2.0)
            try:
                exchange = await run_edu_turn(
                    page,
                    item,
                    profile=profile,
                    project_id=project_id,
                    ws_log=ws_log,
                    index=idx,
                )
                scores = score_educator_exchange(exchange, item, profile=profile)
                exchange["scores"] = scores
                scores_by_id[item["id"]] = scores

                shot_path = SCREENSHOT_DIR / f"{idx + 1:02d}_{item['id']}.png"
                await page.screenshot(path=str(shot_path), full_page=True)
                exchange["screenshot"] = str(shot_path.relative_to(REPO_ROOT))

                eval_data["exchanges"].append(exchange)
                print(
                    f"[EDU] {item['id']} grade={scores['grade']} pass={scores['pass']}"
                )
            except Exception as exc:
                print(f"[EDU] {item['id']} FAILED: {exc}")
                eval_data["exchanges"].append(
                    {"prompt_id": item["id"], "status": "error", "error": str(exc)}
                )

        await browser.close()

    OUTPUT_DATA.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_DATA.write_text(json.dumps(eval_data, indent=2), encoding="utf-8")
    report_path = write_report(eval_data, scores_by_id)
    print(f"\n[EDU] Report: {report_path}")
    print(f"[EDU] Data: {OUTPUT_DATA}")


if __name__ == "__main__":
    asyncio.run(main())
