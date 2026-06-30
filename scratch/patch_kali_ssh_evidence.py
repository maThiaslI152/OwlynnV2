import re

with open("src/tools/screen_assist/kali_ssh.py", "r") as f:
    content = f.read()

# Make run_remote_kali_command save evidence and truncate return
import_stmt = "from src.memory.pentest_engagement import get_active_engagement, store_evidence\nimport time\n"
if "get_active_engagement" not in content:
    content = content.replace("import uuid\n", "import uuid\n" + import_stmt)

old_timeout_return = """    # Timeout — return whatever we captured last
    return (
        f"(command timed out after {timeout}s)\\n{last_output[-2000:]}"
        if last_output
        else f"Error: Command timed out after {timeout}s"
    )"""
new_timeout_return = """    # Timeout — return whatever we captured last
    final_output = last_output if last_output else f"Error: Command timed out after {timeout}s"
    return _process_output_for_evidence(final_output, command, timed_out=True)"""

content = content.replace(old_timeout_return, new_timeout_return)

old_success_return_1 = """                return "\\n".join(output_lines) if output_lines else "(no output)"
            elif marker_line_idx >= 0:
                # Couldn't find command line, return everything before marker
                output_lines = lines[:marker_line_idx]
                while output_lines and not output_lines[-1].strip():
                    output_lines.pop()
                return "\\n".join(output_lines) if output_lines else "(no output)" """
new_success_return_1 = """                final_output = "\\n".join(output_lines) if output_lines else "(no output)"
                return _process_output_for_evidence(final_output, command)
            elif marker_line_idx >= 0:
                # Couldn't find command line, return everything before marker
                output_lines = lines[:marker_line_idx]
                while output_lines and not output_lines[-1].strip():
                    output_lines.pop()
                final_output = "\\n".join(output_lines) if output_lines else "(no output)"
                return _process_output_for_evidence(final_output, command)"""
content = content.replace(old_success_return_1, new_success_return_1)

helper = """
def _process_output_for_evidence(output: str, command: str, timed_out: bool = False) -> str:
    \"\"\"Save full output to evidence store and return a truncated preview.\"\"\"
    eng = get_active_engagement()
    if not eng:
        # If no engagement, just truncate it to 2000 chars and return
        if len(output) > 2000:
            return output[:1000] + "\\n... [OUTPUT TRUNCATED - NO ACTIVE ENGAGEMENT] ...\\n" + output[-1000:]
        return output

    # Save to evidence
    content_bytes = f"Command: {command}\\n\\n{output}".encode("utf-8")
    
    # Extract binary name for filename
    binary = command.split()[0].split("/")[-1] if command else "command"
    filename = f"{binary}_output.log"
    
    sha = store_evidence(eng["id"], content_bytes, filename, "text/plain")
    
    # Truncate for LLM context (50 lines or ~2000 chars)
    lines = output.split("\\n")
    if len(lines) > 50:
        preview = "\\n".join(lines[:25]) + "\\n\\n... [OUTPUT TRUNCATED (Saved to Evidence)] ...\\n\\n" + "\\n".join(lines[-25:])
    elif len(output) > 2000:
        preview = output[:1000] + "\\n\\n... [OUTPUT TRUNCATED (Saved to Evidence)] ...\\n\\n" + output[-1000:]
    else:
        preview = output
        
    status = " (TIMED OUT)" if timed_out else ""
    return f"[Command Output{status}]\\n{preview}\\n\\n[Full output saved to evidence_store: {sha}]"
"""
if "def _process_output_for_evidence" not in content:
    content = content + helper

with open("src/tools/screen_assist/kali_ssh.py", "w") as f:
    f.write(content)
