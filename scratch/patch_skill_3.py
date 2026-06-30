with open(".agents/skills/pentest_workflow/SKILL.md", "r") as f:
    content = f.read()

rule_6 = """
6. **CLEAN ENVIRONMENTS & ROCKYOU**: Between engagements, or at the start of a new one, use `kali_reset_vm()` to wipe the VM's home directory and ensure a clean state.
   - When brute-forcing, use `/usr/share/wordlists/rockyou.txt`. If the tool complains it doesn't exist, it may be zipped. Run `run_kali_command('sudo gzip -d /usr/share/wordlists/rockyou.txt.gz')` first.
"""

if "CLEAN ENVIRONMENTS & ROCKYOU" not in content:
    content += rule_6

with open(".agents/skills/pentest_workflow/SKILL.md", "w") as f:
    f.write(content)
