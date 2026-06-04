# Long Conversation Evaluation — Initial Run

- **Date:** 2026-06-04
- **Model:** Qwen3.5 0.8B + 9B Q6_K
- **Mode:** API with thread_id persistence
- **Hardware:** M4 Air 24GB on battery, no cooling → thermal throttling
- **Completed:** 6/17 exchanges

## Results

| Turn | Topic | Duration | Chars | Model | Notes |
|------|-------|----------|------|-------|-------|
| L1.1 | WebSocket vs SSE | 227s | 4415 | 9B medium | Detailed comparison ✅ |
| L1.2 | Chat scaling | 10s | 711 | 0.8B small | Good follow-up ✅ |
| L1.3 | Security | 11s | 912 | 0.8B small | Concise ✅ |
| L1.4 | Python server | 12s | 1084 | 0.8B small | Code provided ✅ |
| L1.5 | Reconnection logic | 176s | 1805 | 9B medium | Detailed code ✅ |
| L1.6 | Cloud deployment | 160s | 1849 | 9B medium | Good ✅ |

## Key Findings

1. **Thread persistence works** — L1.2 referenced prior WebSocket discussion
2. **Thermal throttling on battery** — medium model calls slow to 160-227s
3. **Routing splits correctly** — complex tasks → 9B, simple follow-ups → 0.8B
4. **0 errors** — all 6 responses were valid and on-topic
5. **Remaining 11 prompts timed out** due to thermal throttling accumulation

## Recommendation

Run long evaluation on AC power with the M4 Air elevated for airflow. Expected: 60-120s per medium model call, enabling full 17-prompt completion.
