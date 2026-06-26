#!/usr/bin/env python3
"""
Model evaluation sweep — tests each LM Studio model for router + fallback.

Unloads all non-embedding models, loads one at a time, restarts backend,
runs a 6-turn eval subset, collects results, generates comparison report.

Usage:
  PYTHONPATH=. python scripts/eval_local_models.py              # all models
  PYTHONPATH=. python scripts/eval_local_models.py --tier B,C    # specific tiers
  PYTHONPATH=. python scripts/eval_local_models.py --model "gemma-4-e4b-*"
  PYTHONPATH=. python scripts/eval_local_models.py --dry-run

Requires:
  - LM Studio running on :1234
  - Frontend running on :5173
  - Playwright installed
"""

from __future__ import annotations

import argparse
import asyncio
import fnmatch
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
LM_STUDIO_API = "http://127.0.0.1:1234"
BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://127.0.0.1:5173"
PYTHON_BIN = sys.executable  # current Python interpreter

EVAL_IDS = "F1.1,F8.1,F3.1,F4.1,F6.1,F7.1"
EVAL_TIMEOUT_S = 900  # 15 min per model max
HEALTH_TIMEOUT_S = 120  # 2 min for backend to become ready
MODEL_LOAD_TIMEOUT_S = 120  # 2 min for LM Studio to load model

DATA_DIR = REPO_ROOT / "data"
RESULTS_DIR = DATA_DIR / "model_sweep"
SCREENSHOT_BASE = REPO_ROOT / "assets"


# ── Model definitions ──────────────────────────────────────────────────────

@dataclass
class ModelConfig:
    id: str                          # LM Studio model identifier
    display_name: str                # Human-readable name
    tier: str                        # S/A/B/C/D/E
    model_type: str = "llm"          # llm, vlm
    arch: str = ""                   # gemma4, qwen35, qwen35moe, llama
    quantization: str = ""           # 4bit, Q4_K_M, Q6_K, Q8_0, etc.
    estimated_vram_gb: float = 0.0   # Estimated VRAM when loaded
    max_context_length: int = 131072 # Model's max context from LM Studio
    load_context_length: int = 16384 # Context to request at load time
    flash_attention: bool = True     # GGUF only
    num_experts: int | None = None   # MoE only — active experts at inference
    capabilities: list[str] = field(default_factory=lambda: ["tool_use"])
    notes: str = ""                  # Quirks, known issues
    skip: bool = False               # Skip this model in the sweep


MODELS: list[ModelConfig] = [
    # ── Baseline (current production model) ──────────────────────────────
    ModelConfig(
        id="gemma-4-e2b-heretic-uncensored-mlx",
        display_name="Gemma-4 E2B Heretic (MLX 4bit)",
        tier="A",
        arch="gemma4",
        quantization="4bit",
        estimated_vram_gb=3.5,
        max_context_length=131072,
        load_context_length=8192,  # MLX default — can't override via API
        flash_attention=False,  # N/A for MLX
        notes="Current production baseline. MLX models ignore context_length/flash_attention in load API.",
    ),
    # ── Tier B: 4B models ────────────────────────────────────────────────
    ModelConfig(
        id="gemma-4-e4b-it-ultra-uncensored-heretic-mlx-mixed_4_6",
        display_name="Gemma-4 E4B Ultra Uncensored (MLX mixed)",
        tier="B",
        arch="gemma4",
        quantization="4bit",
        estimated_vram_gb=5.0,
        max_context_length=131072,
        load_context_length=8192,
        flash_attention=False,
        notes="MLX mixed quantization. 2x size of E2B. May improve reasoning/router accuracy.",
    ),
    ModelConfig(
        id="qwen3-vl-4b-instruct-c_abliterated-v2-mlx",
        display_name="Qwen3 VL 4B Instruct (MLX 4bit)",
        tier="B",
        model_type="vlm",
        arch="qwen3_vl",
        quantization="4bit",
        estimated_vram_gb=5.0,
        max_context_length=262144,
        load_context_length=16384,
        flash_attention=False,
        capabilities=["tool_use"],
        notes="Vision-language model. May route differently due to vision training. MLX runtime.",
    ),
    # ── Tier C: MoE models (high capacity, low active params) ────────────
    ModelConfig(
        id="qwen3.6-35b-a3b-uncensored-hauhaucs-aggressive",
        display_name="Qwen3.6 35B MoE A3B Aggressive (GGUF)",
        tier="C",
        model_type="vlm",
        arch="qwen35moe",
        quantization="unknown",
        estimated_vram_gb=20.0,  # 35B params full weight, even with MoE
        max_context_length=262144,
        load_context_length=16384,
        flash_attention=True,
        num_experts=3,
        skip=True,  # 35B params ≈ 20 GB VRAM — too large for 24 GB M4 Air
        notes="SKIP: 35B total ≈ 20 GB VRAM even at Q4. Won't fit alongside agent/embedding.",
    ),
    ModelConfig(
        id="qwen3.5-18b-a3b-reap-coding-heretic-v0-i1",
        display_name="Qwen3.5 18B MoE A3B Reap Coding (GGUF Q4_K_S)",
        tier="C",
        arch="qwen35moe",
        quantization="Q4_K_S",
        estimated_vram_gb=10.0,
        max_context_length=262144,
        load_context_length=16384,
        flash_attention=True,
        num_experts=3,
        notes="GGUF. 18B total, 3B active. Coding-focused. Previously loaded alongside gemma-4-e2b. Heavy (~10 GB).",
    ),
    ModelConfig(
        id="gemma-4-26b-a4b-it-heretic",
        display_name="Gemma-4 26B MoE A4B Heretic (MLX 4bit)",
        tier="C",
        model_type="vlm",
        arch="gemma4",
        quantization="4bit",
        estimated_vram_gb=12.0,
        max_context_length=262144,
        load_context_length=16384,
        flash_attention=False,
        notes="26B total, 4B active. VLM. Largest MoE Gemma. May be tight on 24 GB with other processes.",
    ),
    # ── Tier D: 9B dense models ──────────────────────────────────────────
    ModelConfig(
        id="qwen3.5-9b-uncensored-hauhaucs-aggressive@q4_k_m",
        display_name="Qwen3.5 9B Dense Aggressive (GGUF Q4_K_M)",
        tier="D",
        model_type="vlm",
        arch="qwen35",
        quantization="Q4_K_M",
        estimated_vram_gb=5.0,
        max_context_length=262144,
        load_context_length=16384,
        flash_attention=True,
        notes="GGUF dense 9B. Good balance of size and capability. Q4_K_M quant.",
    ),
    ModelConfig(
        id="qwen3.5-9b-uncensored-hauhaucs-aggressive@q6_k",
        display_name="Qwen3.5 9B Dense Aggressive (GGUF Q6_K)",
        tier="D",
        model_type="vlm",
        arch="qwen35",
        quantization="Q6_K",
        estimated_vram_gb=7.0,
        max_context_length=262144,
        load_context_length=16384,
        flash_attention=True,
        notes="GGUF dense 9B. Higher quantization than Q4 — better quality, more VRAM.",
    ),
    # ── Tier E: 12B MoE models ──────────────────────────────────────────
    ModelConfig(
        id="gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q6_k",
        display_name="Gemma-4 12B Agentic Fable5 (GGUF Q6_K)",
        tier="E",
        arch="gemma4",
        quantization="Q6_K",
        estimated_vram_gb=9.0,
        max_context_length=262144,
        load_context_length=16384,
        flash_attention=True,
        notes="GGUF 12B MoE agentic-tuned. Has tool_use. Likely strong on tool tasks.",
    ),
    ModelConfig(
        id="gemma-4-12b-coder-fable5-composer2.5-v1@q4_k_m",
        display_name="Gemma-4 12B Coder Fable5 (GGUF Q4_K_M)",
        tier="E",
        arch="gemma4",
        quantization="Q4_K_M",
        estimated_vram_gb=7.0,
        max_context_length=262144,
        load_context_length=16384,
        flash_attention=True,
        notes="GGUF 12B coder-tuned. Has tool_use. Code-focused training may help F3.1/F5.1.",
    ),
    ModelConfig(
        id="gemma-4-12b-coder-fable5-composer2.5-v1@q8_0",
        display_name="Gemma-4 12B Coder Fable5 (GGUF Q8_0)",
        tier="E",
        arch="gemma4",
        quantization="Q8_0",
        estimated_vram_gb=11.0,
        max_context_length=262144,
        load_context_length=16384,
        flash_attention=True,
        notes="GGUF 12B coder Q8 — highest quality quant. Heavy (~11 GB). Tight with other processes.",
    ),
    ModelConfig(
        id="gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q8_0",
        display_name="Gemma-4 12B Agentic Fable5 (GGUF Q8_0)",
        tier="E",
        arch="gemma4",
        quantization="Q8_0",
        estimated_vram_gb=11.0,
        max_context_length=262144,
        load_context_length=16384,
        flash_attention=True,
        capabilities=[],  # NO tool_use!
        notes="GGUF 12B agentic Q8. capabilities=[] — NO tool_use support. Tool tests will fail. Heavy (~11 GB).",
    ),
]


# ── LM Studio API helpers ─────────────────────────────────────────────────

async def lm_studio_list_models() -> list[dict]:
    """List all models with state info."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{LM_STUDIO_API}/api/v0/models")
        resp.raise_for_status()
        return resp.json()["data"]


async def lm_studio_unload(instance_id: str) -> bool:
    """Unload a model by instance_id. Returns True on success."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(
                f"{LM_STUDIO_API}/api/v1/models/unload",
                json={"instance_id": instance_id},
            )
            if resp.status_code == 200:
                print(f"  [LM] Unloaded: {instance_id}")
                return True
            print(f"  [LM] Unload failed ({resp.status_code}): {instance_id}")
            return False
        except Exception as e:
            print(f"  [LM] Unload error: {instance_id} — {e}")
            return False


async def lm_studio_load(model: ModelConfig) -> bool:
    """Load a model with the specified config. Returns True on success."""
    payload: dict[str, Any] = {"model": model.id}

    # GGUF-specific params (ignored by MLX)
    if not model.id.endswith("-mlx"):
        payload["context_length"] = model.load_context_length
        if model.flash_attention:
            payload["flash_attention"] = True
        if model.num_experts is not None:
            payload["num_experts"] = model.num_experts
        payload["echo_load_config"] = True

    print(f"  [LM] Loading: {model.display_name} (ctx={model.load_context_length})...")
    async with httpx.AsyncClient(timeout=MODEL_LOAD_TIMEOUT_S) as client:
        try:
            resp = await client.post(
                f"{LM_STUDIO_API}/api/v1/models/load",
                json=payload,
            )
            if resp.status_code == 200:
                data = resp.json()
                lt = data.get("load_time_seconds", "?")
                ltype = data.get("type", "?")
                lcfg = data.get("load_config", {})
                print(f"  [LM] Loaded in {lt}s (type={ltype})")
                if lcfg:
                    print(f"  [LM]   config: {json.dumps(lcfg, indent=None)}")
                return True
            print(f"  [LM] Load failed ({resp.status_code}): {resp.text[:200]}")
            return False
        except Exception as e:
            print(f"  [LM] Load error: {model.id} — {e}")
            return False


async def lm_studio_unload_all_except_embedding() -> bool:
    """Unload all non-embedding models. Returns True if all unloaded successfully."""
    models = await lm_studio_list_models()
    all_ok = True
    for m in models:
        if m.get("state") != "loaded":
            continue
        if m.get("type") == "embeddings":
            continue
        ok = await lm_studio_unload(m["id"])
        if not ok:
            all_ok = False
    # Verify no non-embedding models remain loaded
    await asyncio.sleep(2.0)
    remaining = await lm_studio_list_models()
    still_loaded = [m for m in remaining if m.get("state") == "loaded" and m.get("type") != "embeddings"]
    if still_loaded:
        print(f"  [LM] WARNING: {len(still_loaded)} models still loaded after unload: {[m['id'] for m in still_loaded]}")
        all_ok = False
    return all_ok


async def lm_studio_get_model_info(model_id: str) -> dict | None:
    """Get model info by id."""
    models = await lm_studio_list_models()
    for m in models:
        if m["id"] == model_id:
            return m
    return None


async def lm_studio_is_loaded(model_id: str) -> bool:
    """Check if a model is loaded."""
    info = await lm_studio_get_model_info(model_id)
    return info is not None and info.get("state") == "loaded"


# ── Backend management ────────────────────────────────────────────────────

def kill_backend() -> None:
    """Kill the backend process on port 8000."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", ":8000"],
            capture_output=True, text=True, timeout=5,
        )
        pids = result.stdout.strip().split("\n")
        pids = [p for p in pids if p.strip()]
        for pid in pids:
            try:
                os.kill(int(pid), signal.SIGKILL)
                print(f"  [BE] Killed PID {pid}")
            except (ProcessLookupError, ValueError):
                pass
    except Exception as e:
        print(f"  [BE] Kill warning: {e}")


def start_backend(model_name: str) -> subprocess.Popen:
    """Start the backend with SMALL_LLM_MODEL_NAME override."""
    env = {**os.environ, "SMALL_LLM_MODEL_NAME": model_name}
    cmd = [PYTHON_BIN, "-m", "uvicorn", "src.api.server:app",
           "--host", "127.0.0.1", "--port", "8000"]
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"  [BE] Started PID {proc.pid} (model={model_name})")
    return proc


async def wait_for_backend_ready(timeout_s: float = HEALTH_TIMEOUT_S) -> bool:
    """Poll /api/health until agent is ready."""
    deadline = time.monotonic() + timeout_s
    print(f"  [BE] Waiting for health (timeout={timeout_s}s)...")
    async with httpx.AsyncClient(timeout=5.0) as client:
        while time.monotonic() < deadline:
            try:
                resp = await client.get(f"{BACKEND_URL}/api/health")
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("agent") == "ready":
                        print("  [BE] Ready!")
                        return True
            except Exception:
                pass
            await asyncio.sleep(2.0)
    print("  [BE] Health check timed out!")
    return False


async def apply_eval_settings() -> None:
    """Apply settings required for automated eval (HITL off, auto_approve)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.put(
            f"{BACKEND_URL}/api/unified-settings",
            json={
                "cloud_escalation_enabled": False,
                "scope_clarification_enabled": False,
                "plan_review_enabled": False,
                "execution_policy": "auto_approve",
            },
        )
    print("  [BE] Eval settings applied (cloud off, HITL off, auto_approve)")


# ── Eval runner ────────────────────────────────────────────────────────────

async def run_eval_for_model(model: ModelConfig, run_index: int) -> dict[str, Any]:
    """Run the eval subset for a single model. Returns parsed results."""
    print(f"\n{'='*80}")
    print(f"  RUNNING EVAL: [{model.tier}] {model.display_name}")
    print(f"  Model ID: {model.id}")
    print(f"{'='*80}")

    # 1. Unload all non-embedding models
    print("\n  [STEP 1] Unloading all non-embedding models...")
    await lm_studio_unload_all_except_embedding()
    await asyncio.sleep(2.0)

    # 2. Load target model
    print("\n  [STEP 2] Loading target model...")
    loaded = await lm_studio_load(model)
    if not loaded:
        print(f"  [FAIL] Could not load {model.id} — skipping")
        return {"model": model.id, "display_name": model.display_name, "status": "load_failed", "exchanges": []}

    # Wait for model to stabilize
    await asyncio.sleep(3.0)

    # 3. Kill backend
    print("\n  [STEP 3] Killing backend...")
    kill_backend()
    await asyncio.sleep(2.0)

    # 4. Start backend with model override
    print("\n  [STEP 4] Starting backend...")
    proc = start_backend(model.id)

    # 5. Wait for backend ready
    print("\n  [STEP 5] Waiting for backend...")
    ready = await wait_for_backend_ready()
    if not ready:
        print(f"  [FAIL] Backend not ready for {model.id} — killing and skipping")
        try:
            os.kill(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return {"model": model.id, "display_name": model.display_name, "status": "backend_timeout", "exchanges": []}

    # 6. Apply eval settings
    print("\n  [STEP 6] Applying eval settings...")
    await apply_eval_settings()
    await asyncio.sleep(2.0)

    # 7. Run eval
    print(f"\n  [STEP 7] Running eval ({EVAL_IDS})...")
    result = run_eval_subprocess(model, run_index)

    # 8. Collect VRAM info
    model_info = await lm_studio_get_model_info(model.id)
    if model_info:
        result["loaded_context"] = model_info.get("loaded_context_length", 0)
        result["max_context"] = model_info.get("max_context_length", 0)
        result["capabilities"] = model_info.get("capabilities", [])
        result["quantization_actual"] = model_info.get("quantization", "")
        result["arch_actual"] = model_info.get("arch", "")

    return result


def run_eval_subprocess(model: ModelConfig, run_index: int) -> dict[str, Any]:
    """Run the eval script as a subprocess. Returns parsed results."""
    eval_script = REPO_ROOT / "scripts" / "run_local_frontier_eval.py"
    cmd = [
        PYTHON_BIN, str(eval_script),
        "--profile", "local",
        "--cloud-off",
        "--ids", EVAL_IDS,
    ]

    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}

    try:
        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=EVAL_TIMEOUT_S,
        )
        stdout = result.stdout
        stderr = result.stderr

        # Parse output data file
        output_file = DATA_DIR / "frontier_eval_run_data.json"
        eval_data = {}
        if output_file.exists():
            with open(output_file) as f:
                eval_data = json.load(f)

        # Move per-model results
        model_dir = RESULTS_DIR / f"{run_index:02d}_{model.id.replace('/', '_').replace('@', '_')}"
        model_dir.mkdir(parents=True, exist_ok=True)

        # Save eval data
        with open(model_dir / "eval_data.json", "w") as f:
            json.dump(eval_data, f, indent=2)

        # Save stdout/stderr
        with open(model_dir / "stdout.txt", "w") as f:
            f.write(stdout)
        with open(model_dir / "stderr.txt", "w") as f:
            f.write(stderr)

        # Move screenshots
        ss_src = SCREENSHOT_BASE / "frontier_eval_screenshots"
        if ss_src.exists():
            ss_dst = model_dir / "screenshots"
            if ss_dst.exists():
                import shutil
                shutil.rmtree(ss_dst)
            import shutil
            shutil.copytree(ss_src, ss_dst)

        # Extract summary
        exchanges = eval_data.get("exchanges", [])
        scored = [e for e in exchanges if e.get("status") == "scored"]
        skipped = [e for e in exchanges if e.get("status") == "skipped"]

        total_score = sum(e.get("scores", {}).get("grade", 0) for e in scored)
        max_score = len(scored) * 100

        per_turn = []
        for e in scored:
            s = e.get("scores", {})
            per_turn.append({
                "id": e.get("prompt_id", ""),
                "topic": e.get("topic", ""),
                "grade": s.get("grade", 0),
                "route_match": s.get("route_match", False),
                "tools_match": s.get("tools_match", False),
                "response_ok": s.get("response_ok", False),
                "dsml_leak": s.get("dsml_leak", False),
                "recall_ok": s.get("recall_ok"),
                "duration_s": e.get("duration_seconds", 0),
                "approx_tps": e.get("approx_tps", 0),
                "route": e.get("route", ""),
                "classification_source": e.get("classification_source", ""),
                "model_badge": e.get("model_badge", ""),
            })

        return {
            "model": model.id,
            "display_name": model.display_name,
            "tier": model.tier,
            "status": "completed",
            "total_score": total_score,
            "max_score": max_score,
            "percentage": round((total_score / max_score) * 100, 1) if max_score else 0,
            "scored_turns": len(scored),
            "skipped_turns": len(skipped),
            "per_turn": per_turn,
            "data_dir": str(model_dir),
        }

    except subprocess.TimeoutExpired:
        print(f"  [FAIL] Eval timed out for {model.id}")
        return {"model": model.id, "display_name": model.display_name, "status": "eval_timeout", "exchanges": []}
    except Exception as e:
        print(f"  [FAIL] Eval error for {model.id}: {e}")
        return {"model": model.id, "display_name": model.display_name, "status": f"error: {e}", "exchanges": []}


# ── Report generator ───────────────────────────────────────────────────────

def generate_report(results: list[dict], date_str: str) -> str:
    """Generate a markdown comparison report."""
    lines = [
        "---",
        "status: active",
        "category: evaluations",
        f"last_updated: {date_str}",
        "---",
        "",
        f"# Local Model Comparison — {date_str}",
        "",
        "> Evaluated 6-turn subset (F1.1, F8.1, F3.1, F4.1, F6.1, F7.1) against each model.",
        "> Profile: `local` (cloud off, auto_approve). Scoring: route(25) + tools(25) + instruction(20) + structure(15) + quality(15).",
        "",
        "## Summary",
        "",
        "| # | Model | Tier | Score | % | Route OK | Tools OK | Avg TPS | Status |",
        "|---|-------|------|-------|---|----------|----------|---------|--------|",
    ]

    sorted_results = sorted(results, key=lambda r: r.get("percentage", 0), reverse=True)

    for i, r in enumerate(sorted_results, 1):
        status = r.get("status", "unknown")
        if status == "completed":
            pct = r.get("percentage", 0)
            total = r.get("total_score", 0)
            max_s = r.get("max_score", 0)
            score_str = f"{total}/{max_s}"

            per_turn = r.get("per_turn", [])
            route_ok = sum(1 for t in per_turn if t.get("route_match"))
            tools_ok = sum(1 for t in per_turn if t.get("tools_match"))
            tps_vals = [t.get("approx_tps", 0) for t in per_turn if t.get("approx_tps", 0) > 0]
            avg_tps = round(sum(tps_vals) / len(tps_vals), 1) if tps_vals else 0

            lines.append(
                f"| {i} | {r.get('display_name', r['model'])} | {r.get('tier', '?')} "
                f"| {score_str} | {pct}% | {route_ok}/{len(per_turn)} | {tools_ok}/{len(per_turn)} "
                f"| {avg_tps} | ✅ |"
            )
        else:
            lines.append(
                f"| {i} | {r.get('display_name', r.get('model', '?'))} | {r.get('tier', '?')} "
                f"| — | — | — | — | — | ❌ {status} |"
            )

    # Per-turn detail
    lines.extend(["", "## Per-Turn Detail", ""])

    for r in sorted_results:
        if r.get("status") != "completed":
            continue
        lines.append(f"### {r.get('display_name', r['model'])} (Tier {r.get('tier', '?')})")
        lines.append("")
        lines.append("| ID | Topic | Grade | Route | Tools | TPS | Duration |")
        lines.append("|----|-------|-------|-------|-------|-----|----------|")
        for t in r.get("per_turn", []):
            route_icon = "✅" if t.get("route_match") else "❌"
            tools_icon = "✅" if t.get("tools_match") else "❌"
            lines.append(
                f"| {t.get('id', '?')} | {t.get('topic', '?')} | {t.get('grade', 0)} "
                f"| {route_icon} {t.get('route', '?')} | {tools_icon} "
                f"| {t.get('approx_tps', 0):.1f} | {t.get('duration_s', 0):.1f}s |"
            )
        lines.append("")

    # Model configs
    lines.extend(["## Model Configurations", ""])
    lines.append("| Model | Type | Arch | Quant | VRAM | Loaded Context | Notes |")
    lines.append("|-------|------|------|-------|------|----------------|-------|")
    for m in MODELS:
        if m.skip:
            continue
        lines.append(
            f"| {m.display_name} | {m.model_type} | {m.arch} | {m.quantization} "
            f"| ~{m.estimated_vram_gb} GB | {m.load_context_length} | {m.notes[:80]}... |"
        )
    lines.append("")

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────

async def cleanup_stuck_models() -> None:
    """Unload all non-embedding models and restart backend with default model."""
    print("[CLEANUP] Unloading all non-embedding models...")
    await lm_studio_unload_all_except_embedding()
    print("[CLEANUP] Killing backend...")
    kill_backend()
    await asyncio.sleep(2.0)
    print("[CLEANUP] Starting backend with default model...")
    default_model = "gemma-4-e2b-heretic-uncensored-mlx"
    proc = start_backend(default_model)
    ready = await wait_for_backend_ready()
    if ready:
        print(f"[CLEANUP] Backend ready with {default_model}")
    else:
        print("[CLEANUP] Backend health check timed out — may need manual restart")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Local model evaluation sweep")
    parser.add_argument(
        "--tier",
        default="",
        help="Comma-separated tiers to test (e.g. B,C,D,E). Default: all.",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Wildcard pattern to match model IDs (e.g. 'gemma-4-e4b-*').",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without running.",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Unload all non-embedding models and restart backend with default model.",
    )
    args = parser.parse_args()

    if args.cleanup:
        await cleanup_stuck_models()
        return

    # Filter models
    tier_filter = {t.strip().upper() for t in args.tier.split(",") if t.strip()} if args.tier else None
    model_filter = args.model.strip() if args.model else None

    selected = []
    for m in MODELS:
        if m.skip:
            continue
        if tier_filter and m.tier not in tier_filter:
            continue
        if model_filter and not fnmatch.fnmatch(m.id, model_filter):
            continue
        selected.append(m)

    if not selected:
        print("[ERROR] No models matched the filter.")
        sys.exit(1)

    print(f"\n{'='*80}")
    print(f"  LOCAL MODEL EVALUATION SWEEP")
    print(f"  {len(selected)} models selected | Eval IDs: {EVAL_IDS}")
    print(f"{'='*80}")
    print()

    for i, m in enumerate(selected):
        print(f"  {i+1:2d}. [{m.tier}] {m.display_name}")
        print(f"      ID: {m.id} | VRAM: ~{m.estimated_vram_gb} GB | ctx: {m.load_context_length}")
        if m.notes:
            print(f"      Notes: {m.notes[:100]}")
        print()

    if args.dry_run:
        print("[DRY RUN] Would run the above models. Exiting.")
        return

    # Check prerequisites
    print("[PRE] Checking prerequisites...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{LM_STUDIO_API}/api/v0/models")
            resp.raise_for_status()
            print("  [OK] LM Studio reachable")
    except Exception as e:
        print(f"  [FAIL] LM Studio not reachable: {e}")
        sys.exit(1)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{FRONTEND_URL}")
            resp.raise_for_status()
            print("  [OK] Frontend reachable")
    except Exception as e:
        print(f"  [FAIL] Frontend not reachable: {e}")
        sys.exit(1)

    # Ensure output dir exists
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Run sweep
    date_str = time.strftime("%Y-%m-%d")
    results: list[dict] = []

    for i, model in enumerate(selected):
        print(f"\n{'#'*80}")
        print(f"  MODEL {i+1}/{len(selected)}")
        print(f"{'#'*80}")

        try:
            result = await run_eval_for_model(model, run_index=i + 1)
        except Exception as e:
            print(f"  [CRASH] Unexpected error for {model.id}: {e}")
            result = {"model": model.id, "display_name": model.display_name, "status": f"crash: {e}", "exchanges": []}
        results.append(result)

        # Save intermediate results
        with open(RESULTS_DIR / "sweep_results.json", "w") as f:
            json.dump(results, f, indent=2)

        print(f"\n  [RESULT] {result.get('display_name', '?')}: "
              f"{result.get('status', '?')} "
              f"({result.get('total_score', 0)}/{result.get('max_score', 0)} = "
              f"{result.get('percentage', 0)}%)")

    # Generate report
    print("\n\n[REPORT] Generating comparison report...")
    report = generate_report(results, date_str)
    report_path = REPO_ROOT / "docs" / "evaluations" / f"local-model-comparison-{date_str}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"  [REPORT] Saved to {report_path}")

    # Final summary
    print(f"\n{'='*80}")
    print(f"  SWEEP COMPLETE — {len(results)} models tested")
    print(f"{'='*80}")
    completed = [r for r in results if r.get("status") == "completed"]
    if completed:
        best = max(completed, key=lambda r: r.get("percentage", 0))
        print(f"  BEST: {best.get('display_name')} ({best.get('percentage', 0)}%)")
    for r in results:
        status = r.get("status", "?")
        pct = f"{r.get('percentage', 0)}%" if status == "completed" else status
        print(f"  [{r.get('tier', '?')}] {r.get('display_name', '?')}: {pct}")


if __name__ == "__main__":
    asyncio.run(main())
