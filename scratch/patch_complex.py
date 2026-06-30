with open("src/agent/core/complex.py", "r") as f:
    content = f.read()

old_guidance = """**Kali CLI Tools (primary execution channel):**
- `run_kali_command` — Execute any command in Kali VM and get output. Use this for ALL Kali tools.
  - Example: `run_kali_command("nmap -sV -sC 10.0.0.1")`
  - Example: `run_kali_command("nikto -h http://10.0.0.1")`
  - Example: `run_kali_command("sqlmap -u http://10.0.0.1/login --batch")`
  - Example: `run_kali_command("hydra -l admin -P /usr/share/wordlists/rockyou.txt 10.0.0.1 ssh")`
- `capture_kali_terminal` — Read existing tmux output (when user ran commands manually)"""

new_guidance = """**Kali CLI Tools & Multi-Window Shells:**
- `kali_tmux_new_window` — Create a new tmux window (e.g., `kali_tmux_new_window("listener")`). Use this to run multiple tools in parallel!
- `kali_tmux_list_windows` — List active windows.
- `run_kali_command` — Execute a command and wait for output. Output is auto-saved to evidence! Use `window="main"` or your custom window.
  - Example: `run_kali_command("nmap -sV -sC 10.0.0.1", window="recon")`
- `send_kali_input` — Send literal keystrokes to an INTERACTIVE tool (e.g. msfconsole or a reverse shell).
  - Example: `send_kali_input("exploit\\n", window="listener")`
- `capture_kali_terminal` — Read the current screen of a window. Useful to check on interactive shells.
  - Example: `capture_kali_terminal(window="listener")`

**Evidence & Reporting:**
- `read_evidence` — Search/read huge tool outputs that were auto-saved to evidence (e.g. a huge nmap scan)."""

content = content.replace(old_guidance, new_guidance)

old_rule = "- Use `capture_kali_terminal` only to read existing tmux output (when user ran commands manually)"
new_rule = "- Use `send_kali_input` for interactive tools! NEVER use `run_kali_command` for a reverse shell listener or msfconsole, as it will hang."

content = content.replace(old_rule, old_rule + "\n" + new_rule)

with open("src/agent/core/complex.py", "w") as f:
    f.write(content)
