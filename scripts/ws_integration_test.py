#!/usr/bin/env python3
"""Integration test: send a rich multi-capability prompt via WebSocket and capture the full flow."""

import asyncio
import json
import websockets
import time
import sys

THREAD_ID = "integration-test-2026-05-27"
WS_URL = f"ws://127.0.0.1:8000/ws/chat/{THREAD_ID}"

TEST_PROMPT = """Compare Python FastAPI vs Express.js for building REST APIs with the following criteria:
- Performance under 1000+ concurrent users
- Type safety and developer experience
- Ecosystem and middleware support
- Learning curve

Please:
1. Create a structured comparison table
2. Visualize the comparison as a mermaid diagram (bar chart or decision tree)
3. Write the full comparison results to a file called `comparison.md` in the workspace
4. Note which one you'd recommend for a project with 1000+ concurrent users that prioritizes type safety
5. Search the web for any recent benchmarks that support your recommendation
6. Remember that I strongly prefer type-safe languages and frameworks

Be thorough and provide concrete data points where possible."""

async def main():
    print(f"[TEST] Connecting to {WS_URL}...")
    
    events_log = []
    start_time = time.monotonic()
    
    async with websockets.connect(WS_URL) as ws:
        print("[TEST] Connected. Sending prompt...")
        
        # Send the test prompt
        payload = {
            "message": TEST_PROMPT,
            "files": [],
            "mode": "tools_on",
            "web_search_enabled": True,
            "project_id": "default",
            "thread_id": THREAD_ID,
        }
        await ws.send(json.dumps(payload))
        print(f"[TEST] Prompt sent ({len(TEST_PROMPT)} chars). Waiting for events...")
        
        done = False
        event_count = 0
        tool_calls_seen = set()
        hitl_interrupts = []
        status_changes = []
        model_info = []
        router_info = None
        
        while not done:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=120.0)
                event = json.loads(raw)
                event_count += 1
                events_log.append(event)
                
                etype = event.get("type", "unknown")
                
                # Track interesting events
                if etype == "status":
                    status = event.get("content", "")
                    status_changes.append(status)
                    print(f"  [STATUS] → {status}")
                    if status == "idle" and event_count > 5:
                        # Give a few seconds for final events to arrive
                        await asyncio.sleep(2)
                        done = True
                        
                elif etype == "chunk":
                    content = event.get("content", "")
                    if content:
                        print(f"  [CHUNK] {content[:120]}{'...' if len(content) > 120 else ''}")
                        
                elif etype == "tool_execution":
                    tool_name = event.get("tool_name", "unknown")
                    status_t = event.get("status", "unknown")
                    tool_calls_seen.add(tool_name)
                    print(f"  [TOOL] {tool_name} → {status_t}")
                    
                elif etype == "interrupt":
                    interrupts = event.get("interrupts", [])
                    for i in interrupts:
                        itype = i.get("type", "unknown") if isinstance(i, dict) else str(i)
                        hitl_interrupts.append(itype)
                    print(f"  [HITL INTERRUPT] {[i.get('type','?') if isinstance(i,dict) else str(i) for i in interrupts]}")
                    
                elif etype == "model_info":
                    model_info.append(event)
                    print(f"  [MODEL] {event.get('model','?')} swap={event.get('swapping',False)}")
                    
                elif etype == "router_info":
                    router_info = event.get("metadata", {})
                    print(f"  [ROUTER] {json.dumps(router_info, indent=2)[:300]}")
                    
                elif etype == "assistant.message":
                    msg = event.get("message", {})
                    content = msg.get("content", "")
                    model = msg.get("model_used", "")
                    tc = msg.get("tool_calls", [])
                    if tc:
                        tool_calls_seen.update(t.get("name", "?") for t in tc)
                    print(f"  [MSG] model={model} tools={[t.get('name','?') for t in tc]} content={content[:100]}...")
                    
                elif etype == "memory_updated":
                    print(f"  [MEMORY] Updated")
                    
                elif etype == "error":
                    print(f"  [ERROR] {event.get('content', '')}")
                    
            except asyncio.TimeoutError:
                print("[TEST] Timeout waiting for events — assuming done.")
                done = True
            except websockets.exceptions.ConnectionClosed:
                print("[TEST] WebSocket connection closed.")
                done = True
    
    elapsed = time.monotonic() - start_time
    
    # Summary
    print("\n" + "="*70)
    print(f"INTEGRATION TEST SUMMARY — {THREAD_ID}")
    print("="*70)
    print(f"Duration: {elapsed:.1f}s")
    print(f"Total events: {event_count}")
    print(f"Status changes: {status_changes}")
    print(f"Tools used ({len(tool_calls_seen)}): {sorted(tool_calls_seen)}")
    print(f"HITL interrupts ({len(hitl_interrupts)}): {hitl_interrupts}")
    print(f"Router info: {json.dumps(router_info) if router_info else 'NONE'}")
    print(f"Model info events: {len(model_info)}")
    if model_info:
        models_used = set(e.get("model", "?") for e in model_info)
        print(f"Models used: {models_used}")
    
    # Check for key expected behaviors
    checks = []
    checks.append(("Router emitted info", router_info is not None))
    checks.append(("Tools were called", len(tool_calls_seen) > 0))
    checks.append(("Web search tool used", "web_search" in tool_calls_seen))
    checks.append(("File write tool used", any("write" in t.lower() for t in tool_calls_seen)))
    checks.append(("Multiple tool types", len(tool_calls_seen) >= 2))
    checks.append(("Status reached idle", "idle" in status_changes))
    
    print("\nChecks:")
    all_pass = True
    for desc, result in checks:
        status = "PASS" if result else "FAIL"
        if not result:
            all_pass = False
        print(f"  [{status}] {desc}")
    
    # Save events log
    log_path = "/tmp/integration_test_events.json"
    with open(log_path, "w") as f:
        json.dump(events_log, f, indent=2, default=str)
    print(f"\nFull event log saved to {log_path}")
    
    return 0 if all_pass else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
