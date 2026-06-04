import re

with open("src/api/server.py", "r") as f:
    content = f.read()

# 1. Update GraphSession signatures
content = content.replace(
    "async def _locked_execute(self, input_data, config):",
    "async def _locked_execute(self, input_data, config, correlation_id=None):"
)
content = content.replace(
    "await self._execute(input_data, config)",
    "await self._execute(input_data, config, correlation_id)"
)
content = content.replace(
    "async def start_run(self, input_data, config):",
    "async def start_run(self, input_data, config, correlation_id=None):"
)
content = content.replace(
    "self.task = asyncio.create_task(self._execute(input_data, config))",
    "self.task = asyncio.create_task(self._execute(input_data, config, correlation_id))"
)
content = content.replace(
    "async def _execute(self, input_data, config):",
    "async def _execute(self, input_data, config, correlation_id=None):"
)
content = content.replace(
    "self.event_buffer.append(start_msg)\n            for q in list(self.listeners):\n                await q.put(start_msg)",
    "self.event_buffer.append((start_msg, correlation_id))\n            for q in list(self.listeners):\n                await q.put((start_msg, correlation_id))"
)
content = content.replace(
    "self.event_buffer.append(event)\n                # Broadcast\n                for q in list(self.listeners):\n                    await q.put(event)",
    "self.event_buffer.append((event, correlation_id))\n                # Broadcast\n                for q in list(self.listeners):\n                    await q.put((event, correlation_id))"
)
content = content.replace(
    "self.event_buffer.append(err_msg)\n            for q in list(self.listeners):\n                await q.put(err_msg)",
    "self.event_buffer.append((err_msg, correlation_id))\n            for q in list(self.listeners):\n                await q.put((err_msg, correlation_id))"
)
content = content.replace(
    "self.event_buffer.append(done_msg)\n            for q in list(self.listeners):\n                await q.put(done_msg)",
    "self.event_buffer.append((done_msg, correlation_id))\n            for q in list(self.listeners):\n                await q.put((done_msg, correlation_id))"
)

# 2. Update forward_events loop extraction
old_forward_events = """
        try:
            while True:
                event = await q.get()
                if event is None: # Sentinel
                    break
"""
new_forward_events = """
        try:
            while True:
                item = await q.get()
                if item is None: # Sentinel
                    break
                event, correlation_id = item if isinstance(item, tuple) else (item, None)
                
                async def _send_ws(payload):
                    if correlation_id and isinstance(payload, dict):
                        payload["correlation_id"] = correlation_id
                    await websocket.send_json(payload)
"""
content = content.replace(old_forward_events, new_forward_events)

# Replace websocket.send_json with _send_ws ONLY within forward_events
start_idx = content.find("async def forward_events():")
end_idx = content.find("forwarder_task = asyncio.create_task(forward_events())")
if start_idx != -1 and end_idx != -1:
    forward_events_body = content[start_idx:end_idx]
    forward_events_body = forward_events_body.replace("websocket.send_json", "_send_ws")
    content = content[:start_idx] + forward_events_body + content[end_idx:]

# 3. Handle websocket receives to extract correlation_id
content = content.replace(
    "await session.start_run(\n                    Command(resume={\"approved\": approved}),\n                    config=config\n                )",
    "await session.start_run(\n                    Command(resume={\"approved\": approved}),\n                    config=config,\n                    correlation_id=payload.get(\"correlation_id\")\n                )"
)
content = content.replace(
    "await session.start_run(\n                    Command(resume={\"answer\": answer}),\n                    config=config\n                )",
    "await session.start_run(\n                    Command(resume={\"answer\": answer}),\n                    config=config,\n                    correlation_id=payload.get(\"correlation_id\")\n                )"
)
content = content.replace(
    "await session.start_run(\n                    Command(resume={\"approved\": approved, \"feedback\": feedback}),\n                    config=config\n                )",
    "await session.start_run(\n                    Command(resume={\"approved\": approved, \"feedback\": feedback}),\n                    config=config,\n                    correlation_id=payload.get(\"correlation_id\")\n                )"
)

content = content.replace(
    "await session.start_run(\n                {\n                    \"messages\": [HumanMessage(content=message_content)],\n                    \"mode\": payload_mode,\n                    \"web_search_enabled\": web_search_enabled,\n                    \"response_style\": response_style,\n                },\n                config\n            )",
    "await session.start_run(\n                {\n                    \"messages\": [HumanMessage(content=message_content)],\n                    \"mode\": payload_mode,\n                    \"web_search_enabled\": web_search_enabled,\n                    \"response_style\": response_style,\n                },\n                config,\n                correlation_id=payload.get(\"correlation_id\")\n            )"
)

with open("src/api/server.py", "w") as f:
    f.write(content)
