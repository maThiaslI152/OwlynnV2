with open(".agents/skills/pentest_workflow/SKILL.md", "r") as f:
    content = f.read()

rule_4_old = """4. **INTERACTIVE SHELLS WILL HANG**: NEVER use `run_kali_command` to start a reverse shell listener (`nc -lvnp`), `msfconsole`, `su`, or any tool that does not exit automatically. It will hang until timeout!
   - **Correct approach for interactive tools**:
     1. Create a new window: `kali_tmux_new_window("listener")`
     2. Send the command: `send_kali_input("nc -lvnp 4444\\n", window="listener")`
     3. Check the screen: `capture_kali_terminal(window="listener")`
     4. Switch back to your main window to trigger the exploit: `run_kali_command("curl http://target/exploit.php", window="main")`"""

rule_4_new = """4. **INTERACTIVE SHELLS WILL HANG**: NEVER use `run_kali_command` to start a reverse shell listener (`nc -lvnp`), `msfconsole`, `su`, or any tool that does not exit automatically. It will hang until timeout!
   - **Correct approach for interactive tools**:
     1. Create a new window: `kali_tmux_new_window("listener")`
     2. Send the command: `send_kali_input("nc -lvnp 4444\\n", window="listener")`
     3. Check the screen: `capture_kali_terminal(window="listener")`
     4. Switch back to your main window to trigger the exploit: `run_kali_command("curl http://target/exploit.php", window="main")`
5. **METASPLOIT & BACKGROUND SHELLS**: Metasploit and reverse shells can be unstable or take time to connect. When using them, be proactive! Use the `/schedule` slash command (or your scheduling tool if available) to periodically check the `listener` window (using `capture_kali_terminal`) to see if the shell has popped or if it disconnected, so you don't lose track of it while doing other tasks."""

content = content.replace(rule_4_old, rule_4_new)

with open(".agents/skills/pentest_workflow/SKILL.md", "w") as f:
    f.write(content)
