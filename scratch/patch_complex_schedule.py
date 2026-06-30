with open("src/agent/core/complex.py", "r") as f:
    content = f.read()

old_schedule = """**Evidence & Reporting:**"""
new_schedule = """**Proactive Monitoring (Background Shells):**
- If you start a reverse shell listener or msfconsole payload that might take a while to connect (or could disconnect), you MUST use the `schedule` tool (e.g. `schedule(DurationSeconds="30", Prompt="Check listener window for popped shell", TimerCondition="any")`) to remind yourself to check the window later using `capture_kali_terminal`. Do not just wait silently!

**Evidence & Reporting:**"""

if "Proactive Monitoring" not in content:
    content = content.replace(old_schedule, new_schedule)

with open("src/agent/core/complex.py", "w") as f:
    f.write(content)
