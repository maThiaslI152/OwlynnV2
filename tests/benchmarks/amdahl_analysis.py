#!/usr/bin/env python3
"""
Amdahl's Law Analysis — LLM Optimization Ceiling
=================================================

Reads ``benchmark_report.json`` (produced by running the benchmark suite)
and computes the LLM-time / total-time ratio per route.

For each route, answers the core question:
  "If I optimize the LLM to be infinitely fast, what's the maximum
   speedup I can achieve?"

Uses Amdahl's Law:  max_speedup = 1 / (1 - parallel_fraction)

Where parallel_fraction = LLM_time / total_time.
The non-LLM fraction (1 - parallel_fraction) is the serial bottleneck.

Usage:
    python tests/benchmarks/amdahl_analysis.py [report_path]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

# ── Route categorization from entry names ─────────────────────────────────

ROUTE_MAP = {
    # Router
    "router_node": "router",
    "router_batch_throughput": "router",
    "router_concurrency": "router",
    "skill_matcher": "router",
    # Simple
    "simple_node": "simple",
    "simple_batch": "simple",
    "simple_fallback": "simple",
    "simple_concurrency": "simple",
    # Complex
    "complex_default": "complex-default",
    "complex_vision": "complex-vision",
    "complex_longctx": "complex-longctx",
    "complex_cloud": "complex-cloud",
    "fallback": "complex-default",
    "postproc": "complex",
    "tool_action": "complex",
    "graph_e2e": "complex",
    # Memory
    "memory": "memory",
    "format_context": "memory",
    # Pool
    "pool": "pool",
    "swap": "pool",
}

# Default mock LLM delays used in benchmarks (ms) per route
# These represent realistic LM Studio inference latencies on Mac M4 Air:
# - Small:  ibm-grok4-ultrafast-coder-1b (1B, ~10-20ms)
# - Medium: gemma-4-e4b-uncensored-hauhaucs-aggressive (4B Q4_K_M, ~50-150ms)
# - Cloud:  DeepSeek API (~200-500ms)
LLM_DELAYS_MS = {
    "router": 15,  # Small LLM (ibm-grok4-1b) — routing prompt is short
    "simple": 15,  # Small LLM (ibm-grok4-1b)
    "complex-default": 80,  # Medium-default (gemma-4-e4b Q4_K_M)
    "complex-vision": 120,  # Medium-vision
    "complex-longctx": 150,  # Medium-longctx
    "complex-cloud": 300,  # Cloud (DeepSeek API)
}


def load_report(path: Optional[Path] = None) -> dict:
    """Load benchmark_report.json."""
    report_path = path or Path(__file__).parent / "benchmark_report.json"
    if not report_path.exists():
        print(f"ERROR: No benchmark report found at {report_path}")
        print("Run the benchmarks first:")
        print("  python -m pytest tests/benchmarks/ -m benchmark -v")
        sys.exit(1)
    return json.loads(report_path.read_text())


def compute_llm_fraction(entry: dict) -> tuple[float, str]:
    """Estimate LLM time fraction for a benchmark entry.

    Uses known mock LLM delay vs total measured latency.
    Returns (fraction, route_or_category).
    """
    name = entry.get("name", "")
    mean_ms = entry.get("mean_ms", 0)
    metadata = entry.get("metadata", {})
    category = entry.get("category", "")

    # Determine route
    route = None
    if category == "router":
        route = "router"
    elif category == "simple":
        route = "simple"
    elif category == "memory":
        route = "memory"
    elif category == "pool":
        route = "pool"
    elif category == "complex":
        # Look at metadata or entry name for route
        route = metadata.get("route", None)
        if not route:
            name_lower = name.lower()
            if "vision" in name_lower:
                route = "complex-vision"
            elif "longctx" in name_lower:
                route = "complex-longctx"
            elif "cloud" in name_lower:
                route = "complex-cloud"
            else:
                route = "complex-default"
    else:
        route = "unknown"

    # Get mock delay for this route
    mock_delay_ms = metadata.get("mock_delay_ms", None) or LLM_DELAYS_MS.get(route, 50)

    if mean_ms <= 0 or mock_delay_ms <= 0:
        return 0.0, route

    # LLM fraction = mock delay / total mean
    # This is approximate — real overhead includes CPU time for system prompt building,
    # tool binding, response parsing, etc.
    fraction = mock_delay_ms / mean_ms
    return min(fraction, 1.0), route


def analyze(report: dict) -> dict:
    """Compute LLM-vs-non-LLM breakdown per route."""
    entries = report.get("entries", [])
    if not entries:
        return {}

    # Collect all timing data per route
    route_data: dict[str, list[float]] = {}
    route_names: dict[str, list[str]] = {}

    for entry in entries:
        fraction, route = compute_llm_fraction(entry)
        if route == "unknown":
            continue
        route_data.setdefault(route, []).append(fraction)
        route_names.setdefault(route, []).append(entry.get("name", "?"))

    # Compute averages per route
    results = {}
    for route in sorted(route_data.keys()):
        fractions = route_data[route]
        if not fractions:
            continue
        avg_llm_pct = sum(fractions) / len(fractions)
        non_llm_pct = 1.0 - avg_llm_pct
        max_speedup = 1.0 / non_llm_pct if non_llm_pct > 0 else float("inf")
        results[route] = {
            "llm_percent": round(avg_llm_pct * 100, 1),
            "non_llm_percent": round(non_llm_pct * 100, 1),
            "max_speedup": round(max_speedup, 2),
            "data_points": len(fractions),
            "source_entries": route_names[route],
        }

    return results


def print_analysis(results: dict, report_path: str):
    """Print the Amdahl analysis in human-readable form."""
    print(f"\nReading report: {report_path}")
    print(
        f"Generated at: {Path(report_path).read_text().split('generated_at')[1].split('"')[2] if '"generated_at"' in Path(report_path).read_text() else 'unknown'}"
    )

    print("\n" + "=" * 80)
    print("  Amdahl's Law Analysis — LLM Optimization Ceiling")
    print("=" * 80)

    if not results:
        print("  No data to analyze. Run the benchmarks first.")
        return

    # Header
    print(
        f"\n  {'Route':<20s} {'LLM %':>7s} {'Non-LLM %':>10s} {'Max Speedup':>12s}  {'Notes'}"
    )
    print(f"  {'─' * 20} {'─' * 7} {'─' * 10} {'─' * 12}  {'─' * 30}")

    for route, data in sorted(results.items()):
        speedup = data["max_speedup"]
        note = ""
        if speedup < 2:
            note = "LLM optimization has limited impact"
        elif speedup < 5:
            note = "LLM optimization is worthwhile"
        elif speedup < 10:
            note = "LLM optimization is high-impact"
        else:
            note = "LLM is the dominant bottleneck"

        print(
            f"  {route:<20s} "
            f"{data['llm_percent']:>6.1f}% "
            f"{data['non_llm_percent']:>9.1f}% "
            f"{speedup:>9.2f}x  "
            f"{note}"
        )

    print("\n" + "=" * 80)
    print("  Interpretation")
    print("=" * 80)
    print("""
  Amdahl's Law: max_speedup = 1 / (1 - parallel_fraction)

  - If LLM is 80% of latency → you can get at most 5x speedup from LLM optimization
  - If LLM is 50% of latency → you can get at most 2x speedup

  To push beyond the ceiling, you must optimize the non-LLM path:
  - Memory injection/write (Qdrant/Mem0 calls)
  - System prompt building
  - Tool binding overhead
  - Anonymization/deanonymization
  - Context trimming
  - Response post-processing

  The ceiling shown above uses mock LLM delays that represent realistic
  LM Studio inference times on Mac M4 Air. Actual results depend on your
  specific hardware and model configuration.
""")

    # Actionable advice
    print("=" * 80)
    print("  Actionable Recommendations")
    print("=" * 80)

    slowest_non_llm = max(
        results.items(), key=lambda x: x[1]["non_llm_percent"], default=None
    )
    if slowest_non_llm:
        route, data = slowest_non_llm
        if data["non_llm_percent"] > 30:
            print(f"\n  Priority 1: Optimize non-LLM path on '{route}' route")
            print(
                f"  ({data['non_llm_percent']:.0f}% of time is spent outside LLM calls)"
            )
            print(
                "  → Profile memory_inject_node, system prompt formatting, response post-processing"
            )

    for route, data in sorted(
        results.items(), key=lambda x: x[1]["max_speedup"], reverse=True
    ):
        if data["max_speedup"] > 5:
            print(
                f"\n  High-leverage: '{route}' route (max {data['max_speedup']}x from LLM optimization)"
            )
            print(
                "  → Consider faster model, quantization, speculative decoding, or pipelining"
            )

    print()


def main():
    report_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    report = load_report(report_path)
    results = analyze(report)
    print_analysis(
        results, str(report_path or Path(__file__).parent / "benchmark_report.json")
    )


if __name__ == "__main__":
    main()
