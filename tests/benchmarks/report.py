"""
Benchmark report collector — percentile computation, throughput stats,
JSON serialization, and human-readable output.

Used by all benchmark test files to accumulate results and write
``benchmark_report.json`` at the end of the run.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_REPORT_DIR = Path(__file__).parent
_DEFAULT_REPORT_PATH = _REPORT_DIR / "benchmark_report.json"


@dataclass
class BenchmarkEntry:
    """A single benchmark result entry."""
    name: str
    category: str  # router | simple | complex | memory | pool
    warmup_iters: int = 2
    measured_iters: int = 50
    concurrency: int = 1
    samples_ms: list[float] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def p50(self) -> float:
        return _percentile(self.samples_ms, 0.50)

    def p95(self) -> float:
        return _percentile(self.samples_ms, 0.95)

    def p99(self) -> float:
        return _percentile(self.samples_ms, 0.99)

    def mean(self) -> float:
        return sum(self.samples_ms) / len(self.samples_ms) if self.samples_ms else 0.0

    def throughput(self) -> float:
        if not self.samples_ms or len(self.samples_ms) < 2:
            return 0.0
        return len(self.samples_ms) / (sum(self.samples_ms) / 1000.0)

    def summary_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "warmup_iters": self.warmup_iters,
            "measured_iters": self.measured_iters,
            "concurrency": self.concurrency,
            "p50_ms": round(self.p50(), 2),
            "p95_ms": round(self.p95(), 2),
            "p99_ms": round(self.p99(), 2),
            "mean_ms": round(self.mean(), 2),
            "throughput_ops_per_sec": round(self.throughput(), 2),
            "metadata": self.metadata,
        }


def _percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    idx = int(len(s) * p)
    if idx >= len(s):
        idx = len(s) - 1
    return s[idx]


# ── Global collector (module-level singleton) ─────────────────────────────

_entries: dict[str, BenchmarkEntry] = {}


def record_entry(entry: BenchmarkEntry) -> None:
    """Record a benchmark entry, merging with existing same-name entries."""
    key = f"{entry.name}-c{entry.concurrency}"
    if key in _entries:
        existing = _entries[key]
        existing.samples_ms.extend(entry.samples_ms)
        existing.measured_iters += entry.measured_iters
        existing.metadata.update(entry.metadata)
    else:
        _entries[key] = entry


def get_entries(category: Optional[str] = None) -> list[BenchmarkEntry]:
    """Get collected entries, optionally filtered by category."""
    entries = list(_entries.values())
    if category:
        entries = [e for e in entries if e.category == category]
    return sorted(entries, key=lambda e: e.name)


def write_report(path: Optional[Path] = None) -> Path:
    """Write collected entries as JSON and return the output path."""
    report_path = path or _DEFAULT_REPORT_PATH
    entries = get_entries()
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_entries": len(entries),
        "entries": [e.summary_dict() for e in entries],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    return report_path


def print_summary(entries: Optional[list[BenchmarkEntry]] = None) -> None:
    """Print a human-readable summary to stdout."""
    entries = entries or get_entries()
    if not entries:
        print("No benchmark entries collected.")
        return

    print("\n" + "=" * 80)
    print("  BENCHMARK RESULTS SUMMARY")
    print("=" * 80)

    for category in ["router", "simple", "complex", "memory", "pool"]:
        cat_entries = [e for e in entries if e.category == category]
        if not cat_entries:
            continue
        print(f"\n--- {category.upper()} ---")
        for entry in cat_entries:
            print(
                f"  {entry.name:<50s} "
                f"p50={entry.p50():>7.1f}ms  "
                f"p95={entry.p95():>7.1f}ms  "
                f"p99={entry.p99():>7.1f}ms  "
                f"thru={entry.throughput():>6.1f}/s"
                f"  (n={entry.measured_iters})"
            )

    print("\n" + "=" * 80)


def clear_entries() -> None:
    """Reset the collector (for test isolation)."""
    _entries.clear()
