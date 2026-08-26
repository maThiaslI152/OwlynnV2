#!/usr/bin/env python3
"""Compare LM Studio speculative draft vs non-speculative for Gemma 4 12B Agentic.

Loads:
  main:  gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m
  draft: gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q8_0  (MTP, ~423M)

Configs compared:
  A) speculative_draft_simple + draft model
  B) no speculative draft

Usage:
  python scripts/manual/bench_speculative_draft.py
  python scripts/manual/bench_speculative_draft.py --rounds 5 --max-tokens 256
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx

LM_STUDIO = "http://127.0.0.1:1234"
MAIN_KEY = "gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m"
DRAFT_KEY = "gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q8_0"
# Absolute GGUF path key as reported by currently-loaded instance config
DRAFT_GGUF = (
    "yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF/"
    "gemma-4-12B-it-MTP-Q8_0.gguf"
)

PROMPTS = [
    {
        "id": "short_fact",
        "messages": [
            {
                "role": "user",
                "content": "Reply with exactly one sentence: what is the capital of France?",
            }
        ],
        "max_tokens": 64,
    },
    {
        "id": "code_fn",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Write a Python function `is_palindrome(s: str) -> bool` "
                    "with a short docstring. No explanation outside the code."
                ),
            }
        ],
        "max_tokens": 256,
    },
    {
        "id": "reasoning",
        "messages": [
            {
                "role": "user",
                "content": (
                    "A bat and a ball cost $1.10 in total. The bat costs $1 more "
                    "than the ball. How much does the ball cost? Show one line of math, "
                    "then the answer."
                ),
            }
        ],
        "max_tokens": 128,
    },
    {
        "id": "toolish",
        "messages": [
            {
                "role": "user",
                "content": (
                    "You are a coding agent. List the next 5 concrete steps to "
                    "debug a FastAPI WebSocket that never emits the idle status event. "
                    "Numbered list only."
                ),
            }
        ],
        "max_tokens": 320,
    },
    {
        "id": "long_gen",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Write a ~200 word explanation of speculative decoding for LLMs, "
                    "including draft model role and acceptance. Plain prose, no bullets."
                ),
            }
        ],
        "max_tokens": 400,
    },
]


def _catalog(client: httpx.Client) -> dict[str, Any]:
    r = client.get(f"{LM_STUDIO}/api/v1/models", timeout=30.0)
    r.raise_for_status()
    return r.json()


def _find_entry(catalog: dict[str, Any], key: str) -> dict[str, Any] | None:
    for m in catalog.get("models") or []:
        if m.get("key") == key:
            return m
    for m in catalog.get("models") or []:
        if key in (m.get("key") or ""):
            return m
    return None


def _loaded_config(key: str, client: httpx.Client) -> dict[str, Any] | None:
    entry = _find_entry(_catalog(client), key)
    if not entry:
        return None
    instances = entry.get("loaded_instances") or []
    if not instances:
        return None
    return instances[0].get("config") or {}


def unload_main(client: httpx.Client) -> None:
    entry = _find_entry(_catalog(client), MAIN_KEY)
    if not entry:
        return
    instances = entry.get("loaded_instances") or []
    if not instances:
        print("  [unload] already unloaded")
        return
    instance_id = instances[0].get("id")
    if not instance_id:
        print("  [unload] no instance id; skipping")
        return
    # Current LM Studio /api/v1/models/unload accepts only instance_id
    payload: dict[str, Any] = {"instance_id": instance_id}
    r = client.post(f"{LM_STUDIO}/api/v1/models/unload", json=payload, timeout=60.0)
    print(f"  [unload] status={r.status_code} body={r.text[:200]}")
    if r.status_code not in (200, 201, 202):
        raise RuntimeError(f"unload failed: {r.status_code} {r.text[:300]}")
    # Wait until gone
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        cfg = _loaded_config(MAIN_KEY, client)
        if cfg is None:
            return
        time.sleep(0.5)
    raise TimeoutError("unload timed out")


def load_main(
    client: httpx.Client,
    *,
    speculative: bool,
    context_length: int,
    draft_model: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": MAIN_KEY,
        "context_length": context_length,
        "flash_attention": True,
        "echo_load_config": True,
    }
    if speculative:
        # This LM Studio build rejects speculative_draft_mtp=true (400).
        # UI uses simple=true + MTP Q8 draft GGUF path — match that exactly.
        payload["speculative_draft_simple"] = True
        payload["speculative_draft_model"] = draft_model
        payload["speculative_draft_max_tokens"] = 16
        payload["speculative_draft_min_continue_probability"] = 0.75
    else:
        payload["speculative_draft_simple"] = False
        payload["speculative_draft_model"] = ""

    print(f"  [load] speculative={speculative} draft={draft_model!r}")
    r = client.post(f"{LM_STUDIO}/api/v1/models/load", json=payload, timeout=300.0)
    print(f"  [load] status={r.status_code}")
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text[:500]}
    print(f"  [load] response: {json.dumps(data, indent=2)[:800]}")
    if r.status_code not in (200, 201, 202):
        raise RuntimeError(f"load failed: {r.status_code} {r.text[:300]}")

    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        cfg = _loaded_config(MAIN_KEY, client)
        if cfg is not None:
            print(f"  [load] active config: {json.dumps(cfg, indent=2)}")
            return cfg
        time.sleep(0.5)
    raise TimeoutError("load poll timed out")


def chat_once(
    client: httpx.Client,
    *,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float = 0.0,
) -> dict[str, Any]:
    payload = {
        "model": MAIN_KEY,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    t0 = time.perf_counter()
    try:
        r = client.post(f"{LM_STUDIO}/v1/chat/completions", json=payload, timeout=180.0)
        elapsed = time.perf_counter() - t0
        body: dict[str, Any]
        try:
            body = r.json()
        except Exception:
            body = {"raw_text": r.text[:1000]}
        if r.status_code != 200:
            return {
                "ok": False,
                "elapsed_s": elapsed,
                "status": r.status_code,
                "error": body,
            }
        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
        usage = body.get("usage") or {}
        stats = body.get("stats") or body.get("timings") or {}
        completion_tokens = int(usage.get("completion_tokens") or 0)
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        details = usage.get("completion_tokens_details") or {}
        reasoning_tokens = int(details.get("reasoning_tokens") or 0)
        tok_s = (completion_tokens / elapsed) if elapsed > 0 and completion_tokens else 0.0
        return {
            "ok": True,
            "elapsed_s": round(elapsed, 3),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "reasoning_tokens": reasoning_tokens,
            "tok_s": round(tok_s, 2),
            "content_preview": (content or "")[:180].replace("\n", "\\n"),
            "reasoning_preview": (reasoning or "")[:120].replace("\n", "\\n"),
            "finish_reason": choice.get("finish_reason"),
            "usage": usage,
            "stats": stats,
            "keys": sorted(body.keys()),
        }
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return {
            "ok": False,
            "elapsed_s": round(elapsed, 3),
            "error": f"{type(e).__name__}: {e}",
        }


def run_config(
    client: httpx.Client,
    *,
    label: str,
    speculative: bool,
    context_length: int,
    draft_model: str,
    rounds: int,
    max_tokens_override: int | None,
) -> dict[str, Any]:
    print(f"\n{'=' * 72}")
    print(f"CONFIG: {label}")
    print(f"{'=' * 72}")
    unload_main(client)
    cfg = load_main(
        client,
        speculative=speculative,
        context_length=context_length,
        draft_model=draft_model,
    )

    # Warmup (discard)
    print("  [warmup]")
    warm = chat_once(
        client,
        messages=[{"role": "user", "content": "Say OK."}],
        max_tokens=8,
    )
    print(f"  [warmup] {json.dumps({k: warm.get(k) for k in ('ok', 'elapsed_s', 'tok_s', 'error', 'content_preview')})}")

    runs: list[dict[str, Any]] = []
    for round_i in range(1, rounds + 1):
        for prompt in PROMPTS:
            mt = max_tokens_override or int(prompt["max_tokens"])
            print(f"  [r{round_i}/{rounds}] {prompt['id']} max_tokens={mt} ...", flush=True)
            result = chat_once(
                client,
                messages=prompt["messages"],  # type: ignore[arg-type]
                max_tokens=mt,
            )
            result["prompt_id"] = prompt["id"]
            result["round"] = round_i
            runs.append(result)
            if result.get("ok"):
                print(
                    f"    ok  {result['elapsed_s']:.2f}s  "
                    f"{result['completion_tokens']} tok  "
                    f"{result['tok_s']:.1f} tok/s  "
                    f"{result.get('content_preview', '')[:80]}"
                )
            else:
                print(f"    FAIL {result}")

    ok_runs = [r for r in runs if r.get("ok")]
    fail_runs = [r for r in runs if not r.get("ok")]
    tok_s_vals = [float(r["tok_s"]) for r in ok_runs if r.get("tok_s")]
    elapsed_vals = [float(r["elapsed_s"]) for r in ok_runs]
    completion_vals = [int(r["completion_tokens"]) for r in ok_runs]

    summary = {
        "label": label,
        "speculative": speculative,
        "load_config": cfg,
        "total_runs": len(runs),
        "ok": len(ok_runs),
        "failed": len(fail_runs),
        "avg_tok_s": round(statistics.mean(tok_s_vals), 2) if tok_s_vals else None,
        "median_tok_s": round(statistics.median(tok_s_vals), 2) if tok_s_vals else None,
        "p90_tok_s": (
            round(sorted(tok_s_vals)[max(0, int(len(tok_s_vals) * 0.9) - 1)], 2)
            if tok_s_vals
            else None
        ),
        "avg_elapsed_s": round(statistics.mean(elapsed_vals), 3) if elapsed_vals else None,
        "total_completion_tokens": sum(completion_vals),
        "failures": fail_runs,
        "runs": runs,
    }
    print(
        f"\n  SUMMARY {label}: ok={summary['ok']}/{summary['total_runs']} "
        f"avg={summary['avg_tok_s']} tok/s median={summary['median_tok_s']} tok/s"
    )
    return summary


def resolve_draft_model(client: httpx.Client) -> str:
    """Prefer the GGUF path used by the currently-loaded instance; else catalog key."""
    cfg = _loaded_config(MAIN_KEY, client)
    if cfg and cfg.get("speculative_draft_model"):
        return str(cfg["speculative_draft_model"])
    entry = _find_entry(_catalog(client), DRAFT_KEY)
    if entry:
        # Some LM Studio builds accept the catalog key; keep GGUF path as fallback
        return DRAFT_GGUF
    return DRAFT_GGUF


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--context-length", type=int, default=16384)
    parser.add_argument(
        "--order",
        choices=["spec-first", "base-first"],
        default="spec-first",
        help="Which config to measure first (default: currently-loaded speculative)",
    )
    parser.add_argument(
        "--keep-final",
        choices=["spec", "base", "none"],
        default="spec",
        help="Reload this config at the end (default: restore speculative)",
    )
    args = parser.parse_args()

    out_dir = Path(__file__).resolve().parents[2] / "data" / "model_bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"speculative_compare_{stamp}.json"

    with httpx.Client() as client:
        # Health
        try:
            models = client.get(f"{LM_STUDIO}/v1/models", timeout=10.0)
            models.raise_for_status()
        except Exception as e:
            print(f"LM Studio not reachable at {LM_STUDIO}: {e}", file=sys.stderr)
            return 1

        draft_model = resolve_draft_model(client)
        print(f"Main : {MAIN_KEY}")
        print(f"Draft: {draft_model}")
        print(f"Rounds={args.rounds} ctx={args.context_length}")

        configs = [
            ("speculative_q4_plus_mtp_q8", True),
            ("non_speculative_q4", False),
        ]
        if args.order == "base-first":
            configs = list(reversed(configs))

        results: list[dict[str, Any]] = []
        for label, speculative in configs:
            results.append(
                run_config(
                    client,
                    label=label,
                    speculative=speculative,
                    context_length=args.context_length,
                    draft_model=draft_model,
                    rounds=args.rounds,
                    max_tokens_override=args.max_tokens,
                )
            )

        # Restore preferred ending state
        if args.keep_final == "spec":
            print("\n[restore] reloading speculative config")
            unload_main(client)
            load_main(
                client,
                speculative=True,
                context_length=args.context_length,
                draft_model=draft_model,
            )
        elif args.keep_final == "base":
            print("\n[restore] reloading non-speculative config")
            unload_main(client)
            load_main(
                client,
                speculative=False,
                context_length=args.context_length,
                draft_model=draft_model,
            )

    # Comparison table
    print("\n" + "=" * 72)
    print("COMPARISON")
    print("=" * 72)
    for r in results:
        print(
            f"{r['label']:32s}  ok={r['ok']}/{r['total_runs']}  "
            f"avg={r['avg_tok_s']}  median={r['median_tok_s']}  "
            f"p90={r['p90_tok_s']}  avg_s={r['avg_elapsed_s']}"
        )
        draft = (r.get("load_config") or {}).get("speculative_draft_model")
        simple = (r.get("load_config") or {}).get("speculative_draft_simple")
        mtp = (r.get("load_config") or {}).get("speculative_draft_mtp")
        print(f"  load: simple={simple} mtp={mtp} draft={draft!r}")

    if len(results) == 2 and results[0].get("avg_tok_s") and results[1].get("avg_tok_s"):
        by_label = {r["label"]: r for r in results}
        spec = by_label.get("speculative_q4_plus_mtp_q8")
        base = by_label.get("non_speculative_q4")
        if spec and base and spec["avg_tok_s"] and base["avg_tok_s"]:
            speedup = spec["avg_tok_s"] / base["avg_tok_s"]
            print(f"\nSpeedup (spec / base): {speedup:.2f}x")

    payload = {
        "timestamp": stamp,
        "main": MAIN_KEY,
        "draft": draft_model,
        "rounds": args.rounds,
        "context_length": args.context_length,
        "results": results,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
