---
last_verified: 2026-05-26
auto_generated: false
---

# Owlynn Enhanced Chat — Quick Start Guide

## Overview

Owlynn chat supports code highlighting (190+ languages), rich text formatting, tool execution visibility, model information badges, and real-time streaming via WebSocket.

## Entry Points

```text
http://127.0.0.1:8000                         # Browser access
frontend-v2/src/App.tsx                        # React app shell
frontend-v2/src/lib/wsClient.ts                # WebSocket client
src/api/server.py                              # Backend streaming
```

## Configuration

### DeepSeek API Key (Cloud Escalation)

```bash
export DEEPSEEK_API_KEY=sk-...
```

Or: Settings → Profile → Cloud section (masked field). Cloud escalation is optional — all local models work without it.

### Redis (Short-Term Memory Backend)

```bash
docker-compose up -d
redis-cli ping
```

Expected output: `PONG`. Falls back to in-memory `MemorySaver` if Redis unavailable.

### Settings Access

| Section | Fields |
|---------|--------|
| Profile | Name, language, response style, medium model variants, cloud (DeepSeek) configuration |
| Advanced | Cloud escalation toggle, anonymization toggle, Router HITL, clarification threshold, custom sensitive terms |
| Memory | Short-term (Redis URL), long-term (Mem0/Qdrant) |
| Persona | Agent name, tone of voice |

## API

### Render Capabilities

| Feature | Detail |
|---------|--------|
| Code highlighting | 190+ languages, dark theme (VS Code style), triggered by markdown code fences |
| Rich text | Tables, lists, bold, italic, `inline code` |
| Math | KaTeX-compatible equation rendering |
| Links | Formatted clickable links |
| Tool execution cards | Colored cards showing input, output, duration, status (running/success/error) |
| Model badge | Response footer showing which model was used |

### Status Indicators

| Color | Meaning |
|-------|---------|
| Yellow | Tool is currently executing |
| Green | Tool completed successfully |
| Red | Tool failed or had an error |
| Purple | Model information badge |

### Message Areas

| Color | Content |
|-------|---------|
| Orange/Anthropic | Assistant responses & tool execution |
| Light Gray | User messages |
| Dark Gray | Code blocks and terminal output |
| Red | Errors and warnings |

### Interactive Features

| Feature | Behavior |
|---------|----------|
| Copy button | Copies response content to clipboard, shows "✅ Copied" for 2 seconds |
| Regenerate button | Re-runs the last query, removes current response, sends same prompt again |
| Message actions | `📋 Copy  ↻ Regenerate  🔹 model-name` at bottom of each AI response |

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Syntax highlighting in browser | Fast, zero server overhead | Requires highlight.js bundle |
| WebSocket streaming for real-time UX | Immediate token display | Connection management complexity |
| DOMPurify sanitization | XSS protection | Slight rendering overhead |

## Testing

### Troubleshooting

| Issue | Check |
|-------|-------|
| Code not highlighting | Use proper markdown: ` ```python`. Check `console.log(hljs)` returns an object. Refresh page |
| Tool cards not showing | Tool calls rendered via `type: "message"` events (`AIMessage.tool_calls`, `ToolMessage` outputs). `type: "tool_execution"` is optional. Check WS connection (green dot in sidebar) |
| Model badge not showing | `type: "model_info"` emitted by backend after node completion. Verify WS connection. Check browser console |
| Memory panel "Loading..." indefinitely | No timeout/error fallback — known as BUG-3. Refresh page or restart backend |

### Browser Support

| Browser | Status |
|---------|--------|
| Chrome/Chromium (latest) | Supported |
| Firefox (latest) | Supported |
| Safari (latest) | Supported |
| Edge (latest) | Supported |
| Mobile (iOS Safari, Chrome Android) | Supported |

### Mobile Experience

- Full responsive design
- Touch-friendly buttons
- Swipe to dismiss modals
- Optimized message display
- Settings accessible on small screens

### Security

| Measure | Detail |
|---------|--------|
| HTML sanitization | DOMPurify on all rendered content |
| XSS protection | Sanitized user input |
| Tool execution | Security proxy gates sensitive operations |
| WebSocket | Secure connections recommended |
