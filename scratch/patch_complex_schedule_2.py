with open("src/agent/core/complex.py", "r") as f:
    content = f.read()

old_schedule = """**Proactive Monitoring (Background Shells):**
- If you start a reverse shell listener or msfconsole payload that might take a while to connect (or could disconnect), you MUST use the `schedule` tool (e.g. `schedule(DurationSeconds="30", Prompt="Check listener window for popped shell", TimerCondition="any")`) to remind yourself to check the window later using `capture_kali_terminal`. Do not just wait silently!"""

new_schedule = """**Proactive Monitoring (Background Shells):**
- If you start a reverse shell listener or msfconsole payload that might take a while to connect (or could disconnect), you MUST ask the user to use the `/schedule` slash command (e.g. "Please type `/schedule every 30 seconds: check the listener window`") to remind you to check the window later using `capture_kali_terminal`. Do not just wait silently!"""

content = content.replace(old_schedule, new_schedule)

with open("src/agent/core/complex.py", "w") as f:
    f.write(content)
