# Debugging: LLM Pool & SwapManager

**Quick Reference:** Three-tier LLM architecture managed by `src/agent/llm.py` (LLMPool) and `src/agent/swap_manager.py` (SwapManager). Models served via LM Studio on port 1234. Cloud via DeepSeek API. Key files: `src/agent/llm.py`, `src/agent/swap_manager.py`, `src/agent/router/budget.py`.

## Common Failure Modes

| Symptom | Likely Cause | Diagnostic | Fix |
|---------|-------------|-----------|-----|
| `httpx.ConnectError` to `127.0.0.1:1234` | LM Studio not running | `curl http://127.0.0.1:1234/v1/models` | Launch LM Studio, ensure it's on port 1234 |
| `model_not_found` in response | Model not loaded in LM Studio | `curl http://127.0.0.1:1234/v1/models \| jq '.data[].id'` | Load model in LM Studio or update profile model keys |
| Small LLM response is garbage | Wrong model loaded or token limit | Check response content, compare with expected model | Verify `small_llm_model_name` in profile matches loaded model |
| Swap hangs (>120s) | LM Studio native API unresponsive | `curl http://127.0.0.1:1234/api/v1/models` (native API) | Restart LM Studio; check `docker stats` for memory pressure |
| `ModelSwapError` on swap | Model not found in LM Studio or OOM | Check swap_manager logs for `instance_id` and target model key | Ensure target model is downloaded in LM Studio; free VRAM |
| Swap timeout (120s) | LM Studio slow to load model | Monitor `GET /api/v1/models` during swap | Increase poll timeout in swap_manager or reduce model size |
| DeepSeek API 401 | Invalid or missing API key | `echo $DEEPSEEK_API_KEY` | Set `DEEPSEEK_API_KEY` env var or in User_Profile |
| DeepSeek API 403 | Account quota exceeded or disabled | Check DeepSeek dashboard | Top up quota or disable cloud escalation |
| DeepSeek API 429 | Rate limited | Response includes `Retry-After` header | Wait and retry; system auto-retries after 2s |
| Token budget exceeded mid-response | Response longer than allocated | Check `token_budget_update` WS event | Increase budget in router or reduce response length |
| Context window overflow (prompt too long) | Too many messages/tools in context | Check `active_tokens` in state | Reduce conversation length or force summarization |
| OOM / swap thrashing | Too many models loaded simultaneously | `memory_pressure`, `vm_stat` | Unload unused models; reduce context window |

## Diagnostic Commands

### LM Studio Health

```bash
# Check if LM Studio is reachable (OpenAI-compatible API)
curl -s http://127.0.0.1:1234/v1/models | python3 -c "
import sys,json
data = json.load(sys.stdin).get('data',[])
print(f'Models available: {len(data)}')
for m in data:
    print(f'  - {m[\"id\"]}')
"

# Check LM Studio native API (used by SwapManager)
curl -s http://127.0.0.1:1234/api/v1/models | python3 -c "
import sys,json
data = json.load(sys.stdin)
loaded = data.get('loaded_instances',[])
print(f'Loaded instances: {len(loaded)}')
for inst in loaded:
    print(f'  - {inst.get(\"model_key\",\"?\")} (instance: {inst.get(\"instance_id\",\"?\")})')
"

# List downloaded models in LM Studio (if lms CLI is available)
lms ls 2>/dev/null || echo "lms CLI not available"

# Check LM Studio process status
lms ps 2>/dev/null || echo "lms CLI not available"
```

### DeepSeek API

```bash
# Test DeepSeek API connectivity
curl -s -w "\nHTTP %{http_code}" https://api.deepseek.com/v1/models \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY" | tail -3

# Check if key is configured
echo "Key configured: $([ -n \"$DEEPSEEK_API_KEY\" ] && echo YES || echo NO)"
python3 -c "
from src.memory.user_profile import get_profile
p = get_profile()
dk = p.get('deepseek_api_key','')
print(f'Profile key: {\"SET\" if dk else \"NOT SET\"}')
print(f'Cloud escalation: {p.get(\"cloud_escalation_enabled\",True)}')
"
```

### Memory / VRAM

```bash
# Check memory pressure (macOS)
memory_pressure

# Check VM statistics
vm_stat | head -10

# Check LM Studio memory usage
ps aux | grep "LM Studio" | grep -v grep | awk '{printf "PID: %s, RSS: %.1f GB\n", $2, $6/1024/1024}'

# Check all Python processes
ps aux | grep python | grep -v grep | awk '{printf "PID: %s, RSS: %.1f GB, CMD: %s\n", $2, $6/1024/1024, $11}'
```

## Log Interpretation

### SwapManager Logs

Normal swap sequence:
```
INFO:src.agent.swap_manager:Swap requested: default -> vision
INFO:src.agent.swap_manager:Querying loaded models at http://127.0.0.1:1234/api/v1/models
INFO:src.agent.swap_manager:Unloading instance <instance_id> (gemma-4-e4b-uncensored-hauhaucs-aggressive)
INFO:src.agent.swap_manager:Loading target model: gemma-4-e4b-uncensored-hauhaucs-aggressive
INFO:src.agent.swap_manager:Waiting for model to appear in loaded_instances...
INFO:src.agent.swap_manager:Model loaded successfully after 8s
INFO:src.agent.swap_manager:Swap complete: default -> vision (10.2s total)
```

Swap failure (model not found):
```
INFO:src.agent.swap_manager:Loading target model: nonexistent-model
ERROR:src.agent.swap_manager:Load failed: HTTP 404 — model not found
ERROR:src.agent.swap_manager:ModelSwapError: Failed to load medium model 'nonexistent-model'
```

Swap timeout:
```
INFO:src.agent.swap_manager:Waiting for model to appear in loaded_instances...
WARNING:src.agent.swap_manager:Model not loaded after 120s, giving up
ERROR:src.agent.swap_manager:ModelSwapError: Timeout waiting for model load
```

### LLMPool Logs

```
# Small LLM initialization
INFO:src.agent.llm:Initializing Small_LLM (ibm-grok4-ultrafast-coder-1b)

# Medium LLM init with swap
INFO:src.agent.llm:Requesting medium LLM variant 'vision', current: 'default'
INFO:src.agent.llm:Triggering swap from default to vision

# Cloud LLM usage
INFO:src.agent.llm:Escalating to Cloud_LLM (deepseek-chat)

# Fallback chain
WARNING:src.agent.llm:Cloud LLM failed (401 Unauthorized), falling back to medium-default
INFO:src.agent.llm:model_used=medium-default-fallback, fallback_chain=[cloud{failed:auth}, medium-default{success:fallback}]
```

### Token Budget

```
# Budget allocated by router
INFO:src.agent.router.budget:Token budget allocated: 4096 (input: 512 tokens)

# Budget consumed during streaming
INFO:src.agent.llm:Token budget consumed: 1520/4096 (37%)

# Budget exceeded
WARNING:src.agent.llm:Token budget exceeded: 4200/4096 (102%)

# Cloud budget warning
INFO:src.agent.llm:Cloud budget: 420000/500000 (84%) — WARNING
```

## Step-by-Step Procedures

### Procedure 1: LM Studio Not Reachable

1. Verify LM Studio is running:
   ```bash
   pgrep -fl "LM Studio"
   ```
   Expected: At least one process.

2. If not running, launch LM Studio manually (GUI app).
   - Open LM Studio from Applications.
   - Ensure the local server is started (port 1234).

3. Verify it's on the correct port:
   ```bash
   curl -s http://127.0.0.1:1234/v1/models | head -c 50
   ```
   Expected: `{"object":"list","data":[...`

4. If port is different:
   - Check LM Studio settings for configured port.
   - Update `small_llm_base_url` and `llm_base_url` in profile via `POST /api/profile`.

### Procedure 2: Model Not Found

1. Check what's loaded in LM Studio:
   ```bash
   curl -s http://127.0.0.1:1234/v1/models | python3 -m json.tool | grep '"id"'
   ```

2. Check what the profile expects:
   ```bash
   python3 -c "
   from src.memory.user_profile import get_profile
   p = get_profile()
   print('Small:', p.get('small_llm_model_name'))
   print('Medium default:', p.get('medium_models',{}).get('default'))
   print('Medium vision:', p.get('medium_models',{}).get('vision'))
   print('Medium longctx:', p.get('medium_models',{}).get('longctx'))
   "
   ```

3. If mismatch:
   - Either load the expected model in LM Studio, OR
   - Update the profile to match what's loaded:
     ```bash
     curl -X POST http://127.0.0.1:8000/api/profile \
       -H "Content-Type: application/json" \
       -d '{"small_llm_model_name": "<actual-model-id>"}'
     ```

### Procedure 3: Swap Failure / OOM

1. Check current memory state:
   ```bash
   memory_pressure
   ```
   Expected: Green/normal. If red, VRAM is exhausted.

2. Check what's loaded in LM Studio:
   ```bash
   curl -s http://127.0.0.1:1234/api/v1/models | python3 -c "
   import sys,json
   data = json.load(sys.stdin)
   for inst in data.get('loaded_instances',[]):
       print(f'Loaded: {inst.get(\"model_key\",\"?\")}')
   "
   ```

3. If multiple large models are loaded:
   - Unload all M-tier models except the one needed:
   ```bash
   # Get instance_id of model to keep
   INSTANCE_ID=$(curl -s http://127.0.0.1:1234/api/v1/models | python3 -c "
   import sys,json
   instances = json.load(sys.stdin).get('loaded_instances',[])
   for inst in instances:
       if '1b' not in inst.get('model_key',''):
           print(inst['instance_id'])
           break
   ")
   # Unload it
   curl -X POST http://127.0.0.1:1234/api/v1/models/unload \
     -H "Content-Type: application/json" \
     -d "{\"instance_id\": \"$INSTANCE_ID\"}"
   ```

4. Reduce context window if still OOM:
   - Set a lower `max_tokens` via profile or defer to small LLM for simple queries.
   - The system has a degradation ladder: unload medium → reduce context → disable summarize → terminate SearXNG.

### Procedure 4: DeepSeek API Errors

1. Verify API key:
   ```bash
   echo "Env var: ${DEEPSEEK_API_KEY:0:8}..."
   python3 -c "
   from src.memory.user_profile import get_profile
   p = get_profile()
   print('Profile key:', ('SET' if p.get('deepseek_api_key') else 'NOT SET'))
   "
   ```

2. Test API directly:
   ```bash
   curl -s -w "\nHTTP %{http_code}" https://api.deepseek.com/v1/chat/completions \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer $DEEPSEEK_API_KEY" \
     -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"Hello"}]}' | head -20
   ```

3. Common responses:
   - `401`: Invalid key. Regenerate at DeepSeek dashboard and update `DEEPSEEK_API_KEY`.
   - `403`: Account issue (quota, billing). Check DeepSeek dashboard.
   - `429`: Rate limited. System auto-retries after 2s; if persistent, reduce cloud usage or increase rate limit.

4. Disable cloud escalation temporarily if needed:
   ```bash
   curl -X POST http://127.0.0.1:8000/api/profile \
     -H "Content-Type: application/json" \
     -d '{"cloud_escalation_enabled": false}'
   ```

## Known Fixes

- **`model_not_found` errors for legacy model IDs**: Resolved — profile update semantic now persists active model keys. `LLMPool.clear()` triggered on profile changes.
- **Cloud fallback chain**: All cloud failures auto-retry with Medium_Default. 401/403 suggests checking key. 429 retries after 2s. See [ARCHITECTURE_OVERVIEW.md](../ARCHITECTURE_OVERVIEW.md) section 12.
- See also: [PERFORMANCE_SLOS.md](../PERFORMANCE_SLOS.md) for memory budget and degradation ladder.
