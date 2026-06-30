with open("src/tools/screen_assist/tools.py", "r") as f:
    content = f.read()

# Update capture_kali_terminal
old_capture = """@tool
async def capture_kali_terminal(lines: int = 200) -> str:"""
new_capture = """@tool
async def capture_kali_terminal(window: str = "main", lines: int = 200) -> str:"""
content = content.replace(old_capture, new_capture)

content = content.replace(
    'session=str(kali.get("tmux_session", "main")),',
    'session=str(kali.get("tmux_session", "main")),\n        window=window,',
)

# wait, we have multiple occurrences of session=str(kali.get...
# let's be more precise.
