with open(".agents/skills/pentest_workflow/SKILL.md", "r") as f:
    content = f.read()

rule_5_old = """5. **METASPLOIT & BACKGROUND SHELLS**: Metasploit and reverse shells can be unstable or take time to connect. When using them, be proactive! Use the `/schedule` slash command (or your scheduling tool if available) to periodically check the `listener` window (using `capture_kali_terminal`) to see if the shell has popped or if it disconnected, so you don't lose track of it while doing other tasks."""
rule_5_new = """5. **METASPLOIT & BACKGROUND SHELLS**: Metasploit and reverse shells can be unstable or take time to connect. When using them, be proactive! Since you don't have a schedule tool built-in, you MUST ask the user to use the `/schedule` slash command on your behalf. E.g. "I'm starting a reverse shell listener. Please type `/schedule every 30 seconds: capture_kali_terminal(window='listener')` so I can keep an eye on it in the background!\""""

content = content.replace(rule_5_old, rule_5_new)

with open(".agents/skills/pentest_workflow/SKILL.md", "w") as f:
    f.write(content)
