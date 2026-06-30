with open("src/tools/screen_assist/tools.py", "r") as f:
    content = f.read()

# Fix SCREEN_ASSIST_TOOLS definition since our previous replace failed (it was a list not a tuple)
old_list = """SCREEN_ASSIST_TOOLS = [
    capture_local_terminal,
    read_screen_element,
    get_active_browser_context,
    get_active_browser_screenshot,
    active_browser_action,
    capture_kali_terminal,
    run_kali_command,
    host_browser_action,
    upload_from_workspace,
]"""
new_list = """SCREEN_ASSIST_TOOLS = [
    capture_local_terminal,
    read_screen_element,
    get_active_browser_context,
    get_active_browser_screenshot,
    active_browser_action,
    capture_kali_terminal,
    run_kali_command,
    send_kali_input,
    kali_tmux_new_window,
    kali_tmux_list_windows,
    host_browser_action,
    upload_from_workspace,
]"""

if old_list in content:
    content = content.replace(old_list, new_list)
else:
    print("Could not find exact old_list block")

with open("src/tools/screen_assist/tools.py", "w") as f:
    f.write(content)
