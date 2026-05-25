# Owlynn Agent Benchmark Suite

Stress test and performance benchmark for the Owlynn agent graph's **router**, **simple**, **complex**, and **memory** nodes, plus the **LLM pool** — all using mock LLMs (no live server required).

## Quick Start

```bash
# Run everything (skips slow E2E and concurrency by default)
python tests/benchmarks/run.py --all --quick

# Run specific suite
python tests/benchmarks/run.py --router
python tests/benchmarks/run.py --complex

# Run everything and auto-analyze results
python tests/benchmarks/run.py --all
```

Or with pytest directly:

```bash
# Run all benchmarks
python -m pytest tests/benchmarks/ -m benchmark -v

# Run a single file
python -m pytest tests/benchmarks/test_router_benchmark.py -v

# Skip slow tests (E2E graph, concurrency, batch throughput)
python -m pytest tests/benchmarks/ -m benchmark -v \
  -k "not e2e and not concurrency and not concurrent and not batch_throughput"
```

## What Gets Measured

| Suite | File | What it tests | When to run |
|-------|------|--------------|-------------|
| **Router** | `test_router_benchmark.py` | Small LLM classification latency, token budget accuracy, HITL rate, skill matcher overhead, concurrency throughput | Changes to `router.py`, `llm.py` (small pool), `skills.py` |
| **Simple** | `test_simple_benchmark.py` | Fast-path answer latency by input size, fallback-to-medium overhead, concurrency throughput | Changes to `simple.py` or small LLM pool |
| **Complex** | `test_complex_benchmark.py` | Per-route LLM latency (4 routes), fallback chains, context trimming, post-processing overhead, tool action, E2E graph | Changes to `complex.py`, `llm.py` (medium/cloud), `swap_manager.py`, `anonymization.py`, `tool_sets.py` |
| **Memory** | `test_memory_benchmark.py` | Memory inject/write latency (cache-hit and cold), context formatting cost | Changes to `memory.py`, `memory_manager.py`, `personal_assistant.py` |
| **LLM Pool** | `test_llm_pool_benchmark.py` | Concurrent access lock contention, cold vs warm pool, swap manager simulation | Changes to `llm.py` or `swap_manager.py` |
| **Amdahl** | `amdahl_analysis.py` | LLM-time / total-time ratio per route, theoretical optimization ceiling | After running benchmarks — reads `benchmark_report.json` |

## Models Under Test

| Role | Model | Size | Mock Delay |
|------|-------|------|-----------|
| Small (router, simple) | `ibm-grok4-ultrafast-coder-1b` | 1B | 15ms |
| Medium (complex) | `gemma-4-e4b-uncensored-hauhaucs-aggressive` | 4B Q4_K_M | 80ms |
| Cloud (complex-cloud) | DeepSeek API | — | 300ms |

Delays are realistic estimates for Mac M4 Air with LM Studio. Adjust `delay_ms` values in test files if your hardware differs significantly.

## Understanding the Output

### Console Summary

After any run, you get a table like:

```
--- ROUTER ---
  router_node (len=5)                     p50=    18.2ms  p95=    20.1ms  ...
  router_node (len=74)                    p50=    22.3ms  p95=    25.8ms  ...
  router_batch_throughput                 p50=    17.1ms  p95=    19.3ms  ...
  skill_matcher_latency                   p50=    45.2ms  p95=    68.1ms  ...
```

- **p50**: Median — half of calls are faster than this
- **p95**: 95th percentile — only 5% of calls are slower
- **p99**: 99th percentile — worst-case outlier bound
- **thru**: Throughput in calls/second

### Amdahl's Law Report

The `amdahl_analysis.py` script computes how much of your latency is LLM time vs everything else:

```
Route              | LLM %  | Non-LLM % | Max Speedup | Verdict
complex-cloud      | 99.6%  | 0.4%      | 226.72x     | Cloud API latency dominates
simple             | 81.2%  | 18.8%     | 5.32x       | LLM optimization is high-impact
complex-default    | 56.9%  | 43.1%     | 2.32x       | CPU overhead significant
```

**Interpretation**: If your route shows `Max Speedup = 5x`, it means even an infinitely fast LLM can only make that path 5x faster. To go beyond, you must optimize the non-LLM parts (memory nodes, system prompt building, anonymization, context trimming, etc.).

### JSON Report

`benchmark_report.json` contains raw timing arrays for all runs. The Amdahl analysis reads this file.

### Logs

Timestamped logs are written to `tests/benchmarks/logs/benchmark_YYYYMMDD_HHMMSS.log`.

## When to Run

| Trigger | Suites to run |
|---------|--------------|
| Changed `router.py` | `--router` |
| Changed `simple.py` | `--simple` |
| Changed `complex.py` | `--complex` |
| Changed `memory.py` or memory infra | `--memory` |
| Changed `llm.py` or `swap_manager.py` | `--router --simple --complex --pool` |
| Changed anonymization or `tool_sets.py` | `--complex` |
| Changed `skills.py` | `--router` |
| Before release | `--all` |
| Investigate latency regression | `--all` then `--amdahl` |

## CI Integration

Benchmarks are **excluded from normal CI** via the `benchmark` pytest marker:

```ini
# pytest.ini
markers =
    benchmark: performance/stress tests with mock LLMs (excluded from default CI)
```

```bash
# CI runs without benchmarks:
python -m pytest -m "not network and not benchmark"

# Manually run benchmarks:
python -m pytest tests/benchmarks/ -m benchmark
```

## Extending

### Adding a new route test

Add a `@pytest.mark.parametrize` entry to `TestComplexPerRouteLatency` with a realistic `model_delay`:

```python
@pytest.mark.parametrize("route,model_delay", [
    ("complex-default", 80),
    ("complex-custom", 200),  # your new route
])
```

### Adjusting mock delays for your hardware

Edit the `delay_ms` values in each test file. The conftest `mock_delay` uses milliseconds — higher values simulate slower hardware.

### Adding a new benchmark suite

1. Create `tests/benchmarks/test_your_benchmark.py`
2. Add `@pytest.mark.benchmark` to each test class
3. Import `BenchmarkEntry`, `record_entry` from `report.py`
4. Add suite info to `run.py`'s `BENCHMARKS` dict
5. Add `pytest_sessionfinish` hook if needed
