with open("src/tools/screen_assist/tools.py", "r") as f:
    content = f.read()

reset_tool = """
@tool
async def kali_reset_vm() -> str:
    \"\"\"
    Reset the Kali VM to a clean state.
    
    This is useful between engagements to ensure no files or states leak from one pentest to another.
    Note: This will delete all files in the kali user's home directory and recreate the default tmux session.
    \"\"\"
    if not _enabled():
        return "Error: screen assist is disabled in configuration."

    from src.config.config_loader import config
    import asyncio

    kali = config.get("screen_assist.kali", {})
    host = str(kali.get("host", "") or "").strip()
    if not host:
        return "Error: screen_assist.kali.host is not configured."

    # Execute cleanup script via SSH
    user = str(kali.get("user", "kali"))
    port = int(kali.get("port", 22))
    identity_file = str(kali.get("identity_file", ""))
    
    cmd = "killall tmux; rm -rf /home/kali/*; tmux new-session -d -s main -n shell"
    
    from src.tools.screen_assist.kali_ssh import _ssh_exec
    stdout, stderr, rc = await _ssh_exec(host, user, cmd, port, identity_file, timeout=10.0)
    
    if rc != 0:
        return f"Error: Failed to reset VM: {stderr.strip()}"
    return "Successfully reset Kali VM to a clean state."
"""

if "async def kali_reset_vm" not in content:
    content = content.replace(
        "SCREEN_ASSIST_TOOLS = [", reset_tool + "\nSCREEN_ASSIST_TOOLS = ["
    )

    # also add it to the list
    content = content.replace(
        "    kali_tmux_list_windows,", "    kali_tmux_list_windows,\n    kali_reset_vm,"
    )

with open("src/tools/screen_assist/tools.py", "w") as f:
    f.write(content)
