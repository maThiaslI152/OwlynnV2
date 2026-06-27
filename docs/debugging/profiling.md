---
status: active
category: debugging
last_updated: 2026-05-31
owner: human
---

# Debugging: Profiling & Performance

> **Purpose:** Performance profiling data and analysis.


**Quick Reference:** Resource monitoring and performance profiling for the full Owlynn stack. Targets defined in `docs/PERFORMANCE_SLOS.md` for Mac Air M4 (16 GB). Key metrics: memory (~8.6 GB sustained), latency (simple <2s, complex <8s), throughput (30+ tok/s unified local model, 80+ tok/s small).

## Common Failure Modes

| Symptom | Likely Cause | Diagnostic | Fix |
|---------|-------------|-----------|-----|
| System swap / beachball | Memory exceeded ~14 GB (degradation threshold) | `memory_pressure`, `vm_stat` | Unload unified local model, reduce context window; optionally `podman stop owlynn_searxng` |
| Simple queries > 5s | Small LLM not loaded or LM Studio hung | Check model status in LM Studio | Reload small LLM, restart LM Studio |
| Complex queries > 20s | Unified local model OOM or tool execution slow | Check individual tool timing in WS events | Optimize tool, reduce tools bound, use small LLM fallback |
| First token > 8s | Model cold start or swap in progress | Check `model_info` WS event `swapping` field | Keep unified local model warm, reduce swap frequency |
| CPU > 95% sustained | Infinite loop or CPU-bound tool execution | `top -o cpu`, check backend process | Kill runaway process, check for infinite loops |
| Thermal throttle events | Sustained high CPU/GPU load | `pmset -g thermlog` | Reduce model size, add cooldown between queries |
| Frontend render lags | Too many re-renders or large state updates | React DevTools Profiler | Add memoization, virtualize long lists |
| Docker containers consuming excess memory | Container memory leak or misconfiguration | `docker stats --no-stream` | Restart containers, set memory limits in docker-compose.yml |

## Diagnostic Commands

### Memory Profiling

```bash
# Quick memory snapshot
memory_pressure

# Detailed virtual memory stats
vm_stat | head -15

# Process-level memory (RSS in MB)
ps aux | awk '{printf "%6.1f MB  %s\n", $6/1024, $11}' | sort -rn | head -20

# Focused process memory
echo "=== Python Backend ==="
ps aux | grep "python.*uvicorn" | grep -v grep | awk '{printf "PID: %s, RSS: %.1f GB\n", $2, $6/1024/1024}'

echo "=== LM Studio ==="
ps aux | grep "LM Studio" | grep -v grep | awk '{printf "PID: %s, RSS: %.1f GB\n", $2, $6/1024/1024}'

echo "=== Docker Containers ==="
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}" 2>/dev/null

echo "=== Total System ==="
vm_stat | awk '/Pages active/ {active=$NF} /Pages wired/ {wired=$NF} END {printf "Active+Wired: %.1f GB\n", (active+wired)*4096/1024/1024/1024}'
```

### CPU Profiling

```bash
# Top processes by CPU
top -l 1 -o cpu -n 10 | head -15

# Sample a process (requires sudo on macOS)
sudo sample <pid> 5 -file /tmp/profile.txt 2>/dev/null && echo "Sample saved to /tmp/profile.txt"

# Python-specific profiling with py-spy (if installed)
pip install py-spy 2>/dev/null
py-spy top --pid $(pgrep -f "python.*uvicorn" | head -1) 2>/dev/null

# Check CPU architecture
sysctl -n machdep.cpu.brand_string
sysctl -n hw.perflevel0.logicalcpu_max  # Performance cores
sysctl -n hw.perflevel1.logicalcpu_max  # Efficiency cores
```

### Thermal Monitoring

```bash
# Check thermal state
pmset -g thermlog

# Check if thermal throttling is active
sysctl kern.mitigation.thermal_throttle

# Fan speed (if available)
# M4 Air has no fan, but M4 Pro/Max might
pmset -g fans 2>/dev/null || echo "No fan sensors available (fanless Mac)"
```

### LLM Latency Profiling

```bash
# Measure response latency for a simple query
time python3 -c "
import asyncio
from src.agent.llm import get_small_llm
async def test():
    llm = await get_small_llm()
    result = await llm.ainvoke(['Hello'])
    print(f'Response: {result.content[:50]}...')
asyncio.run(test())
"

# Measure streaming first-token time
python3 -c "
import asyncio, time
from src.agent.llm import get_small_llm
async def test():
    llm = await get_small_llm()
    start = time.time()
    first_token = None
    async for chunk in llm.astream(['Hello']):
        if first_token is None:
            first_token = time.time() - start
        print(chunk.content, end='', flush=True)
    print(f'\nFirst token: {first_token:.2f}s')
asyncio.run(test())
"
```

### Frontend Performance

Open browser DevTools:

1. **Performance tab**: Record a user interaction (send message, switch workspace) → analyze flame graph
2. **React DevTools Profiler**: Record → inspect component render times and reasons
3. **Network tab**: Check bundle sizes, WS message timing

```bash
# Check frontend bundle size
ls -lh frontend-v2/dist/assets/index-*.js frontend-v2/dist/assets/index-*.css 2>/dev/null
du -sh frontend-v2/dist/
```

### Docker Resource Usage

```bash
# Container resource usage
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}" 2>/dev/null

# Check container memory limits
docker inspect qdrant redis searxng --format '{{.Name}}: {{.HostConfig.Memory}}' 2>/dev/null
```

## Log Interpretation

### Memory Pressure States

```
# Normal (green)
The system has normal memory pressure.

# Warning (yellow) — consider reducing model size
The system has moderate memory pressure.
→ Action: check what's consuming memory, consider unloading unified local model

# Critical (red) — immediate action needed
The system has critical memory pressure.
→ Action: unload unified local model, reduce context window; optionally stop SearXNG manually
```

### Thermal Logs

```
# Normal operation
pmset -g thermlog: No thermal warning level recorded

# Throttling active
pmset -g thermlog: CPU_Speed_Limit = 50
→ Action: reduce CPU load, add cooldown between queries
```

### Docker Stats

```
# Example output
NAME      CPU %     MEM USAGE / LIMIT     MEM %
qdrant    2.50%     450MiB / 512MiB       87.9%
redis     0.30%     85MiB / 128MiB        66.4%
searxng   0.50%     180MiB / 256MiB       70.3%
```

If any container approaches its limit, it may be killed by OOM killer. Increase limit in `docker-compose.yml` or investigate memory leak.

### Query Timing (from WebSocket Events)

```
# Normal simple query timing
router_info → chunk (first token in 1.2s) → ... → model_info → status:idle
Total: 2.3s

# Normal complex query timing with tools
router_info → chunk (first token in 2.8s) → tool_execution(2.1s) → chunk → ... → model_info → status:idle
Total: 7.5s

# Slow query (degraded)
router_info → chunk (first token in 6.5s) → ... → model_info → status:idle
Total: 18s → Suggests model swap or OOM pressure
```

## Step-by-Step Procedures

### Procedure 1: Memory Pressure Investigation

1. Check current memory state:
   ```bash
   memory_pressure
   vm_stat | head -10
   ```

2. Identify top memory consumers:
   ```bash
   ps aux | awk '{printf "%6.1f MB  %s\n", $6/1024, $11}' | sort -rn | head -10
   ```

3. Apply degradation ladder (from [PERFORMANCE_SLOS.md](../PERFORMANCE_SLOS.md)):
   - If > 14 GB used: unload unified local model
   - If > 15 GB used: reduce context window to 50K tokens
   - If > 15.5 GB used: disable auto-summarize
   - If < 1 GB free: optionally `podman stop owlynn_searxng` (manual; not automated)

4. To unload unified local model:
   ```bash
   # Via LM Studio native API
   INSTANCE_ID=$(curl -s http://127.0.0.1:1234/api/v1/models | python3 -c "
   import sys,json
   for inst in json.load(sys.stdin).get('loaded_instances',[]):
       if '1b' not in inst.get('model_key',''):
           print(inst['instance_id'])
           break
   ")
   curl -X POST http://127.0.0.1:1234/api/v1/models/unload \
     -H "Content-Type: application/json" \
     -d "{\"instance_id\": \"$INSTANCE_ID\"}"
   ```

### Procedure 2: Query Latency Investigation

1. Measure end-to-end latency:
   - Browser DevTools → Network → WS tab
   - Note timestamp of first client message and last server response
   - Compare against SLOs in [PERFORMANCE_SLOS.md](../PERFORMANCE_SLOS.md)

2. Breakdown by phase:
   - **Router time**: time between client message and `router_info` event
   - **Model time**: time between first and last `chunk` events
   - **Swap time**: indicated by `model_info.swapping = true` and gap in chunks
   - **Tool time**: `tool_execution` event `duration` field

3. If router is slow:
   - Small LLM may be struggling. Check model status in LM Studio.
   - Try restarting LM Studio or switching to a faster small model.

4. If model response is slow:
   - Check for swap activity in `model_info` event
   - Check memory pressure (OOM causes swap thrashing)
   - Reduce context window size

5. If tool execution is slow:
   - Identify the slow tool from `tool_execution` events
   - See [tools.md](tools.md) for tool-specific debugging

### Procedure 3: Frontend Render Profiling

1. Open React DevTools → Profiler tab
2. Click record, perform the action, stop recording
3. Analyze:
   - **Render count**: components that re-render excessively
   - **Render duration**: components that take too long
   - **Commit reason**: why the render was triggered

4. Common frontend performance issues:
   - **Zustand store causing full tree re-renders**: Use selectors to subscribe to specific slices
   - **Missing `useCallback`/`useMemo`**: Functions/values recreated on every render
   - **Large lists without virtualization**: Use `react-window` or `react-virtuoso`
   - **Expensive markdown rendering**: Debounce or use incremental rendering

### Procedure 4: Docker Container Over-Resource

1. Check container resource usage:
   ```bash
   docker stats --no-stream
   ```

2. If a container is using too much memory:
   ```bash
   # Check container logs for errors
   docker logs <container> --tail 50

   # Restart the container
   docker restart <container>

   # Increase memory limit (edit docker-compose.yml)
   # Under the service, add:
   #   mem_limit: 512m  (or appropriate value)
   ```

3. If Qdrant is slow or growing:
   - Check collection size: `curl http://localhost:6333/collections/<name>`
   - Delete old/unused collections if needed
   - Vacuum/optimize if Qdrant supports it

## Known Fixes

- **Memory budget defined**: See [PERFORMANCE_SLOS.md](../PERFORMANCE_SLOS.md) for full resource budget and degradation ladder.
- **Latency targets**: Simple <2s, complex <8s, first token <3s, tool execution <5s. See [PERFORMANCE_SLOS.md](../PERFORMANCE_SLOS.md).
- **Fanless M4 Air**: No thermal throttling expected. If CPU > 95% sustained, investigate infinite loops or CPU-bound operations.
- **SLO check commands**: Pre-commit quick check and pre-release full check documented in [PERFORMANCE_SLOS.md](../PERFORMANCE_SLOS.md).

## Related

- [`docs/debugging/README.md`](README.md) — debugging index

## Last updated

2026-05-31 — `docs-standards-timeline` added frontmatter
