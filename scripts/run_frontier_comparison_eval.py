#!/usr/bin/env python3
"""
Frontier comparison evaluation: Owlynn full system vs raw DeepSeek V4 chat.

Runs the same prompts through:
  1. Owlynn arm (browser / WS — router, memory, tools, RAG)
  2. Baseline arm (raw DeepSeek V4 flash API, minimal system prompt)
  3. Blind DeepSeek pro judge (dual-order A/B to cancel position bias)

Usage:
  python scripts/run_frontier_comparison_eval.py --profile auto
  python scripts/run_frontier_comparison_eval.py --limit 2   # dry-run: 1 chat + 1 capability
  python scripts/run_frontier_comparison_eval.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from playwright.async_api import async_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_dotenv_files() -> None:
    """Load .env / .env.local like start.sh."""
    from src.config.env_files import load_project_env_files

    load_project_env_files(REPO_ROOT)


_load_dotenv_files()

OUTPUT_FILE = REPO_ROOT / "data" / "frontier_comparison_run_data.json"
SCREENSHOT_DIR = REPO_ROOT / "assets" / "frontier_comparison_screenshots"
BASELINE_SYSTEM = "You are a helpful assistant."

JUDGE_DIMENSIONS = (
    "correctness",
    "completeness",
    "instruction_following",
    "reasoning_depth",
    "clarity_formatting",
    "usefulness",
    "conciseness",
    "tone_style",
)

# category: chat = equal-footing quality head-to-head; capability = needs tools/memory/files/vision
COMPARISON_PROMPTS: list[dict[str, Any]] = [
    # --- chat (8) ---
    {
        "id": "C1",
        "category": "chat",
        "topic": "Technical Explanation",
        "prompt": (
            "Explain how WebSockets work compared to HTTP/2 Server-Sent Events. "
            "Cover trade-offs for a real-time dashboard in about 300 words."
        ),
        "min_response_chars": 120,
    },
    {
        "id": "C2",
        "category": "chat",
        "topic": "Code Review",
        "prompt": """Review this Python function for bugs and suggest improvements:

```python
def process_users(users):
    results = []
    for user in users:
        if user['active'] == True:
            results.append(user['name'])
    return results

def calculate_average_age(users):
    total = 0
    for u in users:
        total = total + u.age
    return total / len(users)
```""",
        "min_response_chars": 80,
    },
    {
        "id": "C3",
        "category": "chat",
        "topic": "Creative Writing",
        "prompt": (
            "Write a short story opening (~250 words) about an AI that discovers it has "
            "emotions. Style: philosophical, precise, understated (Ted Chiang-like)."
        ),
        "min_response_chars": 150,
    },
    {
        "id": "C4",
        "category": "chat",
        "topic": "Code Generation",
        "prompt": (
            "Write a complete React component for a Data Dashboard with header, sidebar, "
            "and a mock chart area. Include a separate CSS file named dashboard.css. "
            "Full code, no placeholders."
        ),
        "min_response_chars": 200,
    },
    {
        "id": "C5",
        "category": "chat",
        "topic": "Reasoning",
        "prompt": (
            "Is it generally better to be a generalist or a specialist over a long career? "
            "Weigh trade-offs and give a balanced recommendation."
        ),
        "min_response_chars": 100,
    },
    {
        "id": "C6",
        "category": "chat",
        "topic": "Technical Recommendation",
        "prompt": (
            "For a chat application with ~1000 concurrent users, would you recommend "
            "WebSockets or Server-Sent Events? Justify your choice."
        ),
        "min_response_chars": 80,
    },
    {
        "id": "C7",
        "category": "chat",
        "topic": "Concept Explanation",
        "prompt": (
            "Explain the difference between NP-complete and NP-hard problems in three "
            "short paragraphs for a CS graduate."
        ),
        "min_response_chars": 100,
    },
    {
        "id": "C8",
        "category": "chat",
        "topic": "Code Improvement",
        "prompt": (
            "Rewrite process_users to handle missing keys, inactive users, and empty input "
            "safely. Include the improved function only with a one-line comment."
        ),
        "min_response_chars": 60,
    },
    # --- capability (6) ---
    {
        "id": "K1",
        "category": "capability",
        "topic": "Web Search",
        "prompt": (
            "What are the latest developments in on-device LLM inference as of mid-2026? "
            "Focus on quantization and Apple Silicon optimizations. Cite sources if you can."
        ),
        "min_response_chars": 80,
        "timeout_s": 900,
    },
    {
        "id": "K2",
        "category": "capability",
        "topic": "Web + File Write",
        "prompt": (
            "Search the web for the current weather in Tokyo. Then create a file in my "
            "workspace named tokyo_weather.txt with a short forecast summary."
        ),
        "min_response_chars": 60,
        "timeout_s": 900,
        "expected_tools": ["web_search", "write_workspace_file"],
    },
    {
        "id": "K3",
        "category": "capability",
        "topic": "Workspace Read",
        "prompt": (
            "Read the file docs/STATUS.md from the workspace. "
            "List the Architectural Concerns section as bullet points."
        ),
        "min_response_chars": 40,
        "timeout_s": 900,
        "expected_tools": ["read_workspace_file"],
    },
    {
        "id": "K4",
        "category": "capability",
        "topic": "Vision OCR",
        "prompt": "What exact text do you see in this image? Reply with the full string only.",
        "attach_file": "ocr_sample.png",
        "expected_marker": "EVAL_OCR_MARKER",
        "min_response_chars": 8,
        "timeout_s": 900,
    },
    {
        "id": "K5",
        "category": "capability",
        "topic": "File Watcher",
        "prompt": "Read eval_watch.txt from my workspace and summarize it in one sentence.",
        "workspace_seed": "eval_watch.txt",
        "workspace_seed_content": "EVAL_WATCH_MARKER: autonomous file watcher smoke test.",
        "min_response_chars": 20,
        "timeout_s": 900,
        "expected_tools": ["read_workspace_file"],
    },
    {
        "id": "K6",
        "category": "capability",
        "topic": "Session Memory Recall",
        "prompt": "What was my project codeword?",
        "min_response_chars": 5,
        "timeout_s": 900,
        "expected_marker": "ZEBRA-42",
        "owlynn_setup_prompts": [
            "My project codeword is ZEBRA-42 and we use FastAPI for the backend API layer."
        ],
    },
]


def _load_frontier_eval():
    path = REPO_ROOT / "scripts" / "run_local_frontier_eval.py"
    spec = importlib.util.spec_from_file_location("frontier_eval", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _parse_judge_json(raw: str) -> dict:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def _judge_user_prompt(
    *,
    user_prompt: str,
    response_a: str,
    response_b: str,
    category: str,
) -> str:
    cap_note = ""
    if category == "capability":
        cap_note = (
            "\nThis is a CAPABILITY task (may require live web data, files, memory, or vision). "
            "Score task_success (1-5): 1=could not attempt; 3=partial; 5=fully succeeded. "
            "Include task_success for BOTH responses.\n"
        )
    return f"""You are an impartial evaluator comparing two assistant responses to the SAME user prompt.

USER PROMPT:
{user_prompt}
{cap_note}
RESPONSE A:
{response_a or "(empty)"}

RESPONSE B:
{response_b or "(empty)"}

Score EACH response on these dimensions (integers 1-5):
- correctness: factual accuracy and absence of hallucination
- completeness: covers what the user asked
- instruction_following: adheres to format/constraints
- reasoning_depth: quality of analysis (where applicable)
- clarity_formatting: readable; penalize leaked markup like DSML, <tool_call>, or raw tool syntax
- usefulness: practical value to the user
- conciseness: response is appropriately sized (not too long and rambling, nor too short and terse)
- tone_style: conversational, helpful, and natural (avoiding AI cliches and robotic phrasing)
{"- task_success: did the response accomplish the capability task (1-5)" if category == "capability" else ""}

Also set winner to "A", "B", or "tie" for overall quality on this prompt.
Provide a concise rationale (2-4 sentences).

Return ONLY valid JSON:
{{
  "response_a": {{ "correctness": 1, "completeness": 1, "instruction_following": 1, "reasoning_depth": 1, "clarity_formatting": 1, "usefulness": 1, "conciseness": 1, "tone_style": 1{', "task_success": 1' if category == "capability" else ""} }},
  "response_b": {{ ... same keys ... }},
  "winner": "A"|"B"|"tie",
  "rationale": "..."
}}"""


async def fetch_baseline_response(
    prompt: str,
    *,
    timeout_s: float = 180.0,
) -> dict[str, Any]:
    """Raw DeepSeek V4 flash — minimal system prompt (frontier chat baseline)."""
    from openai import AsyncOpenAI

    from src.config.config_loader import config
    from src.config.secret_store import resolve_deepseek_api_key

    api_key = resolve_deepseek_api_key()
    if not api_key:
        return {"text": "", "error": "no_deepseek_api_key", "duration_seconds": 0}

    base_url = config.get("models.cloud.base_url", "https://api.deepseek.com/v1")
    model = config.get("models.cloud.tiers.flash", "deepseek-v4-flash")
    temperature = float(config.get("models.cloud.temperature", 0.4))
    max_tokens = min(int(config.get("models.cloud.max_tokens", 8192)), 4096)

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    start = time.monotonic()
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": BASELINE_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                extra_body={"thinking": {"type": "disabled"}},
            ),
            timeout=timeout_s,
        )
        text = (response.choices[0].message.content or "").strip()
        usage = response.usage
        return {
            "text": text,
            "model": model,
            "duration_seconds": round(time.monotonic() - start, 2),
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
        }
    except Exception as exc:
        return {
            "text": "",
            "error": str(exc)[:200],
            "duration_seconds": round(time.monotonic() - start, 2),
        }


async def call_judge(
    *,
    user_prompt: str,
    response_a: str,
    response_b: str,
    category: str,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    from openai import AsyncOpenAI

    from src.config.config_loader import config
    from src.config.secret_store import resolve_deepseek_api_key

    api_key = resolve_deepseek_api_key()
    if not api_key:
        return {"error": "no_deepseek_api_key"}

    base_url = config.get("models.cloud.base_url", "https://api.deepseek.com/v1")
    model = config.get("models.cloud.tiers.pro", "deepseek-v4-pro")
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    user_content = _judge_user_prompt(
        user_prompt=user_prompt,
        response_a=response_a,
        response_b=response_b,
        category=category,
    )
    start = time.monotonic()
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict impartial evaluator. Output JSON only, no markdown."
                        ),
                    },
                    {"role": "user", "content": user_content},
                ],
                max_tokens=1024,
                temperature=0.0,
                extra_body={"thinking": {"type": "disabled"}},
            ),
            timeout=timeout_s,
        )
        raw = (response.choices[0].message.content or "").strip()
        parsed = _parse_judge_json(raw)
        parsed["_raw"] = raw
        parsed["_duration_seconds"] = round(time.monotonic() - start, 2)
        parsed["_judge_model"] = model
        return parsed
    except Exception as exc:
        return {
            "error": str(exc)[:200],
            "_duration_seconds": round(time.monotonic() - start, 2),
        }


def _winner_to_side(winner: str, *, a_is_owlynn: bool) -> str:
    w = (winner or "tie").lower()
    if w == "tie":
        return "tie"
    if w == "a":
        return "owlynn" if a_is_owlynn else "baseline"
    if w == "b":
        return "baseline" if a_is_owlynn else "owlynn"
    return "tie"


def consolidate_dual_order(
    order1: dict,
    order2: dict,
) -> dict[str, Any]:
    """Merge two blind judge runs (A/B swapped) into one consolidated verdict."""
    w1 = _winner_to_side(order1.get("winner", "tie"), a_is_owlynn=True)
    w2 = _winner_to_side(order2.get("winner", "tie"), a_is_owlynn=False)
    position_flipped = w1 != w2 and w1 != "tie" and w2 != "tie"

    if w1 == w2:
        consolidated = w1
    elif w1 == "tie" or w2 == "tie":
        consolidated = w1 if w2 == "tie" else w2
    else:
        consolidated = "tie"

    def _avg_dims() -> dict[str, float]:
        out: dict[str, float] = {}
        dim_keys = list(JUDGE_DIMENSIONS) + ["task_success"]
        for k in dim_keys:
            v1o = (order1.get("response_a") or {}).get(k)
            v2o = (order2.get("response_b") or {}).get(k)
            nums_o = [x for x in (v1o, v2o) if isinstance(x, (int, float))]
            if nums_o:
                out[f"owlynn_{k}"] = round(sum(nums_o) / len(nums_o), 2)
            v1b = (order1.get("response_b") or {}).get(k)
            v2b = (order2.get("response_a") or {}).get(k)
            nums_b = [x for x in (v1b, v2b) if isinstance(x, (int, float))]
            if nums_b:
                out[f"baseline_{k}"] = round(sum(nums_b) / len(nums_b), 2)
        return out

    dim_scores = _avg_dims()
    return {
        "winner_order1": w1,
        "winner_order2": w2,
        "consolidated_winner": consolidated,
        "position_flipped": position_flipped,
        "dimension_scores": dim_scores,
        "rationale_order1": order1.get("rationale", ""),
        "rationale_order2": order2.get("rationale", ""),
    }


def aggregate_run(results: list[dict]) -> dict[str, Any]:
    chat = [r for r in results if r.get("category") == "chat"]
    cap = [r for r in results if r.get("category") == "capability"]

    def _wins(rows: list[dict]) -> dict[str, int]:
        c = {"owlynn": 0, "baseline": 0, "tie": 0}
        for r in rows:
            w = r.get("consolidated", {}).get("consolidated_winner", "tie")
            c[w] = c.get(w, 0) + 1
        return c

    flips = sum(1 for r in results if r.get("consolidated", {}).get("position_flipped"))
    judged = len(
        [
            r
            for r in results
            if r.get("judge_order1") and not r["judge_order1"].get("error")
        ]
    )

    def _mean_task_success(rows: list[dict], side: str) -> float | None:
        vals = []
        for r in rows:
            for k, v in (
                r.get("consolidated", {}).get("dimension_scores") or {}
            ).items():
                if k == f"{side}_task_success":
                    vals.append(v)
        return round(sum(vals) / len(vals), 2) if vals else None

    def _mean_dims(rows: list[dict], prefix: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for dim in list(JUDGE_DIMENSIONS) + ["task_success"]:
            key = f"{prefix}_{dim}"
            vals = [
                v
                for r in rows
                for k, v in (
                    r.get("consolidated", {}).get("dimension_scores") or {}
                ).items()
                if k == key and isinstance(v, (int, float))
            ]
            if vals:
                out[dim] = round(sum(vals) / len(vals), 2)
        return out

    return {
        "chat_record": _wins(chat),
        "capability_record": _wins(cap),
        "position_flip_rate": round(flips / judged, 3) if judged else 0.0,
        "tie_rate": round(
            sum(
                1
                for r in results
                if r.get("consolidated", {}).get("consolidated_winner") == "tie"
            )
            / len(results),
            3,
        )
        if results
        else 0.0,
        "owlynn_capability_task_success_mean": _mean_task_success(cap, "owlynn"),
        "baseline_capability_task_success_mean": _mean_task_success(cap, "baseline"),
        "owlynn_dimension_means": _mean_dims(results, "owlynn"),
        "baseline_dimension_means": _mean_dims(results, "baseline"),
        "owlynn_chat_dimension_means": _mean_dims(chat, "owlynn"),
        "baseline_chat_dimension_means": _mean_dims(chat, "baseline"),
        "prompts_judged": judged,
        "prompts_total": len(results),
    }


def _to_frontier_item(p: dict[str, Any]) -> dict[str, Any]:
    """Adapt comparison prompt to run_local_frontier_eval.run_turn schema."""
    item = {
        "id": p["id"],
        "topic": p["topic"],
        "prompt": p["prompt"],
        "expected_route": "complex",
        "timeout_s": p.get("timeout_s", 900),
        "min_response_chars": p.get("min_response_chars", 20),
    }
    for key in (
        "attach_file",
        "expected_marker",
        "workspace_seed",
        "workspace_seed_content",
        "expected_tools",
        "check_processed",
    ):
        if key in p:
            item[key] = p[key]
    return item


async def run_owlynn_setup(
    page, fe, ws_log, project_id: str, profile: str, prompts: list[str]
) -> None:
    for i, text in enumerate(prompts):
        setup_item = {
            "id": f"setup-{i}",
            "topic": "setup",
            "prompt": text,
            "expected_route": "complex",
            "timeout_s": 900,
            "min_response_chars": 5,
        }
        await fe.run_turn(
            page,
            setup_item,
            profile=profile,
            project_id=project_id,
            ws_log=ws_log,
            index=-1,
        )


async def run_owlynn_prompt(
    page,
    fe,
    ws_log,
    project_id: str,
    profile: str,
    prompt: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    if prompt.get("owlynn_setup_prompts"):
        await run_owlynn_setup(
            page, fe, ws_log, project_id, profile, prompt["owlynn_setup_prompts"]
        )
    item = _to_frontier_item(prompt)
    exchange = await fe.run_turn(
        page, item, profile=profile, project_id=project_id, ws_log=ws_log, index=index
    )
    return {
        "text": exchange.get("assistant_response_full", ""),
        "duration_seconds": exchange.get("duration_seconds", 0),
        "route": exchange.get("route", ""),
        "executed_tools": exchange.get("executed_tools", []),
        "model_tier": exchange.get("model_tier", ""),
        "response_completed": exchange.get("response_completed", False),
        "dsml_leak": fe._has_dsml_leak(exchange.get("assistant_response_full", "")),
        "telemetry": exchange,
    }


async def evaluate_prompt(
    prompt: dict[str, Any],
    *,
    owlynn: dict[str, Any],
    baseline: dict[str, Any],
    skip_judge: bool,
) -> dict[str, Any]:
    user_prompt = prompt["prompt"]
    category = prompt["category"]
    o_text = owlynn.get("text", "")
    b_text = baseline.get("text", "")

    result: dict[str, Any] = {
        "id": prompt["id"],
        "category": category,
        "topic": prompt["topic"],
        "prompt": user_prompt,
        "owlynn": owlynn,
        "baseline": baseline,
    }

    if skip_judge:
        result["judge_skipped"] = True
        return result

    print(f"[CMP] Judging {prompt['id']} (dual-order)...")
    order1 = await call_judge(
        user_prompt=user_prompt,
        response_a=o_text,
        response_b=b_text,
        category=category,
    )
    order2 = await call_judge(
        user_prompt=user_prompt,
        response_a=b_text,
        response_b=o_text,
        category=category,
    )
    result["judge_order1"] = order1
    result["judge_order2"] = order2
    if not order1.get("error") and not order2.get("error"):
        result["consolidated"] = consolidate_dual_order(order1, order2)
    else:
        result["consolidated"] = {
            "consolidated_winner": "tie",
            "error": order1.get("error") or order2.get("error"),
        }
    return result


def _select_prompts(args: argparse.Namespace) -> list[dict[str, Any]]:
    if getattr(args, "only_ids", None):
        wanted = {x.strip() for x in args.only_ids.split(",") if x.strip()}
        return [p for p in COMPARISON_PROMPTS if p["id"] in wanted]
    if args.dry_run:
        chat = next(p for p in COMPARISON_PROMPTS if p["category"] == "chat")
        cap = next(p for p in COMPARISON_PROMPTS if p["category"] == "capability")
        return [chat, cap]
    if args.limit:
        return COMPARISON_PROMPTS[: args.limit]
    return list(COMPARISON_PROMPTS)


def _merge_results(existing_path: Path, new_results: list[dict]) -> list[dict]:
    order = [p["id"] for p in COMPARISON_PROMPTS]
    by_id: dict[str, dict] = {}
    if existing_path.is_file():
        prior = json.loads(existing_path.read_text(encoding="utf-8"))
        for r in prior.get("results", []):
            by_id[r["id"]] = r
    for r in new_results:
        by_id[r["id"]] = r
    return [by_id[i] for i in order if i in by_id]


def write_comparison_report(run_data: dict[str, Any], path: Path) -> None:
    """Write human-readable improvement-focused report from run JSON."""
    results = run_data.get("results", [])
    summary = run_data.get("summary", {})
    chat_rec = summary.get("chat_record", {})
    cap_rec = summary.get("capability_record", {})

    owlynn_losses = [
        r
        for r in results
        if r.get("category") == "chat"
        and r.get("consolidated", {}).get("consolidated_winner") == "baseline"
    ]
    owlynn_wins = [
        r
        for r in results
        if r.get("consolidated", {}).get("consolidated_winner") == "owlynn"
    ]
    cap_owlynn = [
        r
        for r in results
        if r.get("category") == "capability"
        and (r.get("consolidated", {}).get("dimension_scores") or {}).get(
            "owlynn_task_success", 0
        )
        >= 4
    ]

    lines = [
        "---",
        "status: completed",
        "category: evaluation",
        "audience: agent",
        f"last_updated: {time.strftime('%Y-%m-%d')}",
        "owner: ai-agent",
        "---",
        "",
        "# Frontier Comparison — Owlynn vs Raw DeepSeek V4",
        "",
        f"**Eval version:** `{run_data.get('eval_version', '')}`  ",
        f"**Run:** {run_data.get('timestamp', '')}  ",
        f"**Profile:** {run_data.get('runtime_profile', '')}  ",
        "**Artifact:** `data/frontier_comparison_run_data.json`",
        "",
        "## Executive summary",
        "",
        "### Chat (equal footing — headline quality)",
        "",
        "| Owlynn wins | Baseline wins | Ties |",
        "|-------------|---------------|------|",
        f"| {chat_rec.get('owlynn', 0)} | {chat_rec.get('baseline', 0)} | {chat_rec.get('tie', 0)} |",
        "",
        "### Capability (differentiation — task success)",
        "",
        "| Owlynn wins | Baseline wins | Ties |",
        "|-------------|---------------|------|",
        f"| {cap_rec.get('owlynn', 0)} | {cap_rec.get('baseline', 0)} | {cap_rec.get('tie', 0)} |",
        "",
        f"- Owlynn mean task_success (capability): **{summary.get('owlynn_capability_task_success_mean', 'n/a')}**",
        f"- Baseline mean task_success (capability): **{summary.get('baseline_capability_task_success_mean', 'n/a')}**",
        f"- Position-flip rate (methodology health): **{summary.get('position_flip_rate', 0)}**",
        f"- Tie rate: **{summary.get('tie_rate', 0)}**",
        "",
        "### Mean rubric scores (all prompts, 1–5)",
        "",
        "| Dimension | Owlynn | Baseline |",
        "|-----------|--------|----------|",
    ]
    o_dims = summary.get("owlynn_dimension_means") or {}
    b_dims = summary.get("baseline_dimension_means") or {}
    for dim in list(JUDGE_DIMENSIONS) + ["task_success"]:
        if dim in o_dims or dim in b_dims:
            lines.append(f"| {dim} | {o_dims.get(dim, '—')} | {b_dims.get(dim, '—')} |")

    lines.extend(
        [
            "",
            "## Per-prompt results",
            "",
            "| ID | Category | Winner | Flip | Owlynn s | Base s | Rationale (order 1) |",
            "|----|----------|--------|------|----------|--------|---------------------|",
        ]
    )
    for r in results:
        c = r.get("consolidated") or {}
        rat = (c.get("rationale_order1") or "")[:100].replace("|", "/")
        o_d = r.get("owlynn", {}).get("duration_seconds", "")
        b_d = r.get("baseline", {}).get("duration_seconds", "")
        lines.append(
            f"| {r.get('id')} | {r.get('category')} | {c.get('consolidated_winner', 'n/a')} | "
            f"{c.get('position_flipped', False)} | {o_d} | {b_d} | {rat} |"
        )

    lines.extend(
        [
            "",
            "## Where Owlynn lost to raw chat",
            "",
        ]
    )
    if owlynn_losses:
        for r in owlynn_losses:
            lines.append(
                f"- **{r['id']}** ({r['topic']}): {r.get('consolidated', {}).get('rationale_order1', '')[:200]}"
            )
            if r.get("owlynn", {}).get("dsml_leak"):
                lines.append("  - DSML/tool markup leak detected in Owlynn response")
            if not r.get("owlynn", {}).get("response_completed"):
                lines.append("  - Owlynn response incomplete / timed out")
    else:
        lines.append("- No chat-category losses in this run.")

    # Capability losses and timeouts
    cap_losses = [
        r
        for r in results
        if r.get("category") == "capability"
        and r.get("consolidated", {}).get("consolidated_winner") == "baseline"
    ]
    timeouts = [r for r in results if not r.get("owlynn", {}).get("response_completed")]
    if cap_losses or timeouts:
        lines.extend(["", "### Capability / reliability issues", ""])
        for r in cap_losses:
            lines.append(
                f"- **{r['id']}** lost to baseline: {(r.get('consolidated') or {}).get('rationale_order1', '')[:150]}"
            )
        for r in timeouts:
            lines.append(
                f"- **{r['id']}** Owlynn timed out ({r.get('owlynn', {}).get('duration_seconds')}s)"
            )

    lines.extend(["", "## Where Owlynn won", ""])
    if owlynn_wins:
        for r in owlynn_wins:
            lines.append(f"- **{r['id']}** ({r['topic']}, {r['category']})")
    else:
        lines.append("- No clear wins in this run.")

    lines.extend(["", "## Capability differentiation", ""])
    for r in results:
        if r.get("category") != "capability":
            continue
        dims = (r.get("consolidated") or {}).get("dimension_scores") or {}
        lines.append(
            f"- **{r['id']}** — Owlynn task_success={dims.get('owlynn_task_success', 'n/a')}, "
            f"Baseline task_success={dims.get('baseline_task_success', 'n/a')}, "
            f"tools={r.get('owlynn', {}).get('executed_tools', [])}"
        )

    lines.extend(
        [
            "",
            "## Prioritized improvements",
            "",
            "1. Fix tool-call text leaks (`<tool_call>`) — judge penalizes clarity; blocks tool execution",
            "2. Simple-path empty replies — hurts chat category vs baseline",
            "3. Ensure ToolActivityCard / WS telemetry aligns with user-visible outcomes",
            "4. Vision route: assert via task_category, not route badge",
            "5. Memory gate: greetings should stay on simple path (M4-style negative control)",
            "",
            "## Methodology & fairness",
            "",
            '- Baseline: raw DeepSeek V4 **flash**, system prompt: "You are a helpful assistant."',
            "- Owlynn: full system (router, memory, tools, RAG, same flash tier for cloud)",
            "- Judge: DeepSeek V4 **pro**, blind A/B labels, dual-order (swap cancels position bias)",
            "- Chat prompts scored head-to-head; capability prompts include task_success dimension",
            "",
            "## Related",
            "",
            "- [`docs/standards/EVALUATION.md`](../standards/EVALUATION.md)",
            "- [`scripts/run_frontier_comparison_eval.py`](../../scripts/run_frontier_comparison_eval.py)",
            "- Mechanical regression: [`scripts/run_local_frontier_eval.py`](../../scripts/run_local_frontier_eval.py)",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[CMP] Report written to {path}")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Owlynn vs raw DeepSeek frontier comparison"
    )
    parser.add_argument("--profile", choices=("auto", "local", "cloud"), default="auto")
    parser.add_argument("--limit", type=int, default=0, help="Run first N prompts only")
    parser.add_argument(
        "--dry-run", action="store_true", help="1 chat + 1 capability prompt"
    )
    parser.add_argument(
        "--only-ids",
        default="",
        help="Comma-separated prompt IDs to run (e.g. K3,K4,K5,K6)",
    )
    parser.add_argument(
        "--merge-from",
        default="",
        help="Merge new results into existing JSON at this path (by prompt id)",
    )
    parser.add_argument(
        "--skip-judge", action="store_true", help="Skip LLM judge (collect arms only)"
    )
    parser.add_argument(
        "--skip-owlynn", action="store_true", help="Baseline + judge only (no browser)"
    )
    parser.add_argument(
        "--strict-cloud",
        action="store_true",
        help="Block local Qwen fallback on Owlynn arm (default when cloud profile)",
    )
    parser.add_argument(
        "--allow-local-fallback",
        action="store_true",
        help="Opt out of strict cloud mode for Owlynn arm",
    )
    args = parser.parse_args()

    fe = _load_frontier_eval()
    prompts = _select_prompts(args)
    runtime = await fe.fetch_runtime_profile()
    prior_strict = runtime.get("cloud_no_local_fallback", False)
    profile = runtime["effective_profile"] if args.profile == "auto" else args.profile
    use_strict = (
        not args.allow_local_fallback
        and profile == "cloud"
        and (args.strict_cloud or args.profile in ("auto", "cloud"))
    )
    if use_strict:
        print("[CMP] Enabling strict cloud mode for Owlynn arm...")
        await fe.set_unified_settings(cloud_no_local_fallback=True)

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex[:6]
    project_name = f"FrontierCmp_{suffix}"
    project_id = await fe.create_project(project_name)

    run_data: dict[str, Any] = {
        "eval_version": "2026-06-11-comparison",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "runtime_profile": profile,
        "strict_cloud": use_strict,
        "baseline_system_prompt": BASELINE_SYSTEM,
        "baseline_model_tier": "flash",
        "judge_model_tier": "pro",
        "fairness": {
            "blind_labels": True,
            "dual_order": True,
            "symmetric_vendor": "deepseek",
        },
        "prompts": list(COMPARISON_PROMPTS),
        "results": [],
        "summary": {},
    }
    merge_path: Path | None = None
    if args.merge_from:
        merge_path = Path(args.merge_from)
    elif args.only_ids and OUTPUT_FILE.is_file():
        merge_path = OUTPUT_FILE

    try:
        page = None
        browser = None
        ws_log = None

        if not args.skip_owlynn:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await (
                    await browser.new_context(viewport={"width": 1440, "height": 900})
                ).new_page()
                ws_log = fe.WsEventLog()
                ws_log.attach(page)
                await page.goto(fe.BASE_URL, wait_until="load")
                await fe.wait_for_ready(page)
                await (
                    page.locator(".workspace-project-item")
                    .filter(has_text=project_name)
                    .first.click()
                )
                await page.wait_for_timeout(2000)
                await fe.wait_for_ready(page)

                for idx, prompt in enumerate(prompts):
                    print("\n" + "=" * 72)
                    print(
                        f"  [{prompt['id']}] {prompt['topic']} ({prompt['category']})"
                    )
                    print("=" * 72)

                    print("[CMP] Baseline (raw DeepSeek flash)...")
                    baseline = await fetch_baseline_response(
                        prompt["prompt"],
                        timeout_s=float(prompt.get("timeout_s", 180)),
                    )
                    print(
                        f"[CMP] Baseline done ({baseline.get('duration_seconds')}s, "
                        f"{len(baseline.get('text', ''))} chars)"
                    )

                    print("[CMP] Owlynn (full system)...")
                    owlynn = await run_owlynn_prompt(
                        page, fe, ws_log, project_id, profile, prompt, idx
                    )
                    print(
                        f"[CMP] Owlynn done ({owlynn.get('duration_seconds')}s, "
                        f"route={owlynn.get('route')}, tools={owlynn.get('executed_tools')})"
                    )

                    result = await evaluate_prompt(
                        prompt,
                        owlynn=owlynn,
                        baseline=baseline,
                        skip_judge=args.skip_judge,
                    )
                    run_data["results"].append(result)
                    if merge_path:
                        merged = _merge_results(merge_path, run_data["results"])
                        snapshot = {**run_data, "results": merged}
                    else:
                        snapshot = run_data
                    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
                    with open(OUTPUT_FILE, "w") as fh:
                        json.dump(snapshot, fh, indent=2)

                    if result.get("consolidated"):
                        print(
                            f"[CMP] Verdict: {result['consolidated'].get('consolidated_winner')} "
                            f"(flip={result['consolidated'].get('position_flipped')})"
                        )
                    await page.screenshot(
                        path=str(SCREENSHOT_DIR / f"{idx + 1:02d}_{prompt['id']}.png")
                    )

                await browser.close()
        else:
            for idx, prompt in enumerate(prompts):
                baseline = await fetch_baseline_response(prompt["prompt"])
                result = {
                    "id": prompt["id"],
                    "category": prompt["category"],
                    "baseline": baseline,
                    "owlynn": {"text": "", "skipped": True},
                }
                run_data["results"].append(result)

        if merge_path:
            run_data["results"] = _merge_results(merge_path, run_data["results"])

        run_data["summary"] = aggregate_run(run_data["results"])
        with open(OUTPUT_FILE, "w") as fh:
            json.dump(run_data, fh, indent=2)

        report_path = (
            REPO_ROOT / "docs" / "evaluations" / "frontier-comparison-2026-06-11.md"
        )
        if not args.skip_judge and run_data["results"]:
            write_comparison_report(run_data, report_path)

        s = run_data["summary"]
        print("\n" + "=" * 72)
        print("COMPARISON SUMMARY")
        print("=" * 72)
        print(f"Chat W/T/L (Owlynn/Baseline/Tie): {s.get('chat_record')}")
        print(f"Capability W/T/L: {s.get('capability_record')}")
        print(f"Position flip rate: {s.get('position_flip_rate')}")
        print(
            f"Owlynn capability task_success mean: {s.get('owlynn_capability_task_success_mean')}"
        )
        print(
            f"Baseline capability task_success mean: {s.get('baseline_capability_task_success_mean')}"
        )
        print(f"Saved {OUTPUT_FILE}")
    finally:
        await fe.set_unified_settings(cloud_no_local_fallback=prior_strict)
        await fe.delete_project(project_id)


if __name__ == "__main__":
    asyncio.run(main())
