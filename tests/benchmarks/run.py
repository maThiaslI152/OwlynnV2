#!/usr/bin/env python3
"""
Owlynn Benchmark Runner
========================

Interactive entry point for the Owlynn agent stress test / benchmark suite.
Explains what each test measures, when to run it, and logs results to a
timestamped file.

Usage:
    python tests/benchmarks/run.py              # interactive menu
    python tests/benchmarks/run.py --all        # run everything
    python tests/benchmarks/run.py --router     # router benchmarks only
    python tests/benchmarks/run.py --complex    # complex node benchmarks only
    python tests/benchmarks/run.py --simple     # simple node benchmarks only
    python tests/benchmarks/run.py --memory     # memory node benchmarks only
    python tests/benchmarks/run.py --pool       # LLM pool benchmarks only
    python tests/benchmarks/run.py --amdahl     # run analysis only (needs existing report)
    python tests/benchmarks/run.py --quick      # skip E2E and concurrency tests
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Project root ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BENCH_DIR = PROJECT_ROOT / "tests" / "benchmarks"
REPORT_PATH = BENCH_DIR / "benchmark_report.json"
LOG_DIR = BENCH_DIR / "logs"

# ── Test definitions ──────────────────────────────────────────────────────────

BENCHMARKS = {
    "router": {
        "file": "tests/benchmarks/test_router_benchmark.py",
        "description": "Router node — 5-way LLM classifier that runs on EVERY turn",
        "what_it_tests": [
            "Router LLM latency — first-response delay for small LLM (ibm-grok4-1b)",
            "Token budget accuracy — how precise is estimate_token_budget()",
            "HITL interception rate — how often does the graph pause for user clarification",
            "Skill matcher latency — TF-IDF + keyword scoring overhead",
            "Concurrency throughput — how many routing decisions per second under load",
        ],
        "when_to_run": "After any change to router.py, llm.py (small pool), or skills.py",
    },
    "simple": {
        "file": "tests/benchmarks/test_simple_benchmark.py",
        "description": "Simple node — fast-path answers without tools (~40% of requests)",
        "what_it_tests": [
            "Simple node latency by input size — p50/p95/p99 for short/medium/long prompts",
            "Fallback overhead — penalty when small LLM fails and medium takes over",
            "Concurrency throughput — calls/sec under 1/2/4/8 coroutines",
        ],
        "when_to_run": "After any change to simple.py or the small LLM pool",
    },
    "complex": {
        "file": "tests/benchmarks/test_complex_benchmark.py",
        "description": "Complex node — heavy reasoning loop with tool binding and 4-tier fallback",
        "what_it_tests": [
            "Per-route latency — p50/p95/p99 for default/vision/longctx/cloud routes",
            "Fallback chain coverage — CloudUnavailableError, ModelSwapError, RuntimeError paths",
            "Context trimming efficiency — token reduction from _trim_tool_history",
            "Post-processing overhead — anonymize, deanonymize, think-tag strip, auto workspace read",
            "Tool action throughput — calls/sec through complex_tool_action_node",
            "E2E graph latency — full graph invocation including memory + router + complex",
        ],
        "when_to_run": "After any change to complex.py, llm.py (medium/cloud pool), swap_manager.py, anonymization.py, or tool_sets.py",
    },
    "memory": {
        "file": "tests/benchmarks/test_memory_benchmark.py",
        "description": "Memory nodes — inject (pre-reasoning) and write (post-reasoning)",
        "what_it_tests": [
            "Memory inject latency — cache-cold (Qdrant/Mem0 search) and cache-hit (fast path)",
            "Memory write latency — full save path and gate-skip (trivial greeting) path",
            "Context formatting cost — format_memory_context() with 0/5/20/100 results",
        ],
        "when_to_run": "After any change to memory.py, memory_manager.py, or personal_assistant.py",
    },
    "pool": {
        "file": "tests/benchmarks/test_llm_pool_benchmark.py",
        "description": "LLM pool — singleton caching and model swap manager",
        "what_it_tests": [
            "Concurrent pool access — lock contention under 1/2/4/8 simultaneous get_*llm() calls",
            "Cold vs warm pool — first-call latency vs cached-call latency per slot",
            "Swap manager simulation — simulated unload + load + poll HTTP round-trip",
        ],
        "when_to_run": "After any change to llm.py or swap_manager.py",
    },
}

QUICK_SKIP = "not e2e and not concurrency and not concurrent and not batch_throughput"


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Owlynn Agent Benchmark Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tests/benchmarks/run.py --router          # router benchmarks only
  python tests/benchmarks/run.py --all --quick     # everything, skip slow E2E/concurrency
  python tests/benchmarks/run.py --amdahl          # analysis after benchmarks ran
""",
    )
    parser.add_argument("--all", action="store_true", help="Run all benchmarks")
    parser.add_argument("--router", action="store_true", help="Router benchmarks")
    parser.add_argument("--simple", action="store_true", help="Simple node benchmarks")
    parser.add_argument("--complex", action="store_true", help="Complex node benchmarks")
    parser.add_argument("--memory", action="store_true", help="Memory node benchmarks")
    parser.add_argument("--pool", action="store_true", help="LLM pool benchmarks")
    parser.add_argument("--amdahl", action="store_true", help="Run Amdahl analysis only")
    parser.add_argument("--quick", action="store_true", help="Skip E2E graph and concurrency tests (faster)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose pytest output")
    return parser.parse_args()


# ── Core logic ────────────────────────────────────────────────────────────────

def header(text: str):
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}")


def info(text: str):
    print(f"  → {text}")


def warn(text: str):
    print(f"  ⚠ {text}")


def ok(text: str):
    print(f"  ✓ {text}")


def fail(text: str):
    print(f"  ✗ {text}")


def show_menu():
    """Interactive menu explaining each benchmark."""
    header("Owlynn Agent Benchmark Suite")
    print()
    print("  Models under test:")
    print("    Small:  ibm-grok4-ultrafast-coder-1b (1B)")
    print("    Medium: gemma-4-e4b-uncensored-hauhaucs-aggressive (4B Q4_K_M)")
    print("    Cloud:  DeepSeek API")
    print()
    print("  Available benchmark suites:")
    print()
    for i, (key, bm) in enumerate(BENCHMARKS.items(), 1):
        print(f"  [{i}] {key.upper():8s} — {bm['description']}")
        for item in bm["what_it_tests"]:
            print(f"       • {item}")
        print(f"       Run when: {bm['when_to_run']}")
        print()
    print(f"  [6] AMD AHL   — Compute LLM optimization ceiling (needs existing report)")
    print(f"  [7] ALL       — Run all benchmarks")
    print(f"  [8] ALL+AMD   — Run all benchmarks + Amdahl analysis")
    print(f"  [q] QUIT")
    print()

    choice = input("  Select [1-8/q]: ").strip().lower()
    return choice


def run_pytest(test_file: str, extra_args: list[str] | None = None, quick: bool = False, verbose: bool = False) -> int:
    """Run pytest on a specific test file and return exit code."""
    args = ["python", "-m", "pytest", test_file, "-m", "benchmark"]
    if verbose:
        args.append("-v")
    else:
        args.append("-q")
        args.append("--no-header")
    if quick:
        args.extend(["-k", QUICK_SKIP])
    if extra_args:
        args.extend(extra_args)
    return subprocess.call(args, cwd=str(PROJECT_ROOT))


def run_amdahl():
    """Run Amdahl analysis script."""
    script = BENCH_DIR / "amdahl_analysis.py"
    if not REPORT_PATH.exists():
        warn(f"No benchmark report found at {REPORT_PATH}")
        info("Run benchmarks first, then re-run --amdahl")
        return 1
    header("Amdahl's Law Analysis")
    return subprocess.call(["python", str(script)], cwd=str(PROJECT_ROOT))


def write_log(suites: list[str], exit_codes: list[int], elapsed_s: float):
    """Append a log entry to LOG_DIR."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"benchmark_{timestamp}.log"

    lines = []
    lines.append(f"Owlynn Benchmark Log — {datetime.now().isoformat()}")
    lines.append(f"Duration: {elapsed_s:.1f}s")
    lines.append(f"Suites: {', '.join(suites)}")
    lines.append("")
    for suite, code in zip(suites, exit_codes):
        status = "PASS" if code == 0 else f"FAIL (exit {code})"
        lines.append(f"  {suite:<20s} → {status}")
    lines.append("")

    log_file.write_text("\n".join(lines))
    info(f"Log written to {log_file}")


def main():
    args = parse_args()

    # ── Determine which suites to run ─────────────────────────────────────
    suites_to_run: list[str] = []

    if args.amdahl:
        run_amdahl()
        return

    if args.all:
        suites_to_run = list(BENCHMARKS.keys())
    else:
        for key in BENCHMARKS:
            if getattr(args, key, False):
                suites_to_run.append(key)

    if not suites_to_run:
        choice = show_menu()
        mapping = {
            "1": ["router"], "2": ["simple"], "3": ["complex"],
            "4": ["memory"], "5": ["pool"],
            "6": [], "7": list(BENCHMARKS.keys()),
            "8": list(BENCHMARKS.keys()),
            "q": [],
        }
        suites_to_run = mapping.get(choice, [])
        if choice == "q":
            info("Exiting.")
            return
        if choice == "6":
            run_amdahl()
            return

    if not suites_to_run:
        warn("No suites selected.")
        return

    # ── Run selected suites ───────────────────────────────────────────────
    header(f"Running: {', '.join(suites_to_run)}")
    start = time.time()
    exit_codes: list[int] = []

    for suite in suites_to_run:
        bm = BENCHMARKS[suite]
        print()
        info(f"Suite: {suite.upper()} — {bm['description']}")
        code = run_pytest(bm["file"], quick=args.quick, verbose=args.verbose)
        exit_codes.append(code)
        if code == 0:
            ok(f"{suite.upper()} passed")
        else:
            fail(f"{suite.upper()} FAILED (exit code {code})")

    elapsed = time.time() - start

    # ── Write log ─────────────────────────────────────────────────────────
    write_log(suites_to_run, exit_codes, elapsed)

    # ── Summary ───────────────────────────────────────────────────────────
    header("Summary")
    total = len(exit_codes)
    passed = sum(1 for c in exit_codes if c == 0)
    print(f"  {passed}/{total} suites passed in {elapsed:.1f}s")
    print()

    # ── Amdahl analysis (auto if --all or multiple suites) ────────────────
    run_amdahl_after = args.all or len(suites_to_run) >= 2
    if run_amdahl_after:
        print()
        run_amdahl()


if __name__ == "__main__":
    main()
