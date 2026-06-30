with open("src/tools/pentest_tools.py", "r") as f:
    content = f.read()

read_evidence_func = """
@tool
def read_evidence(evidence_hash: str, query: str = "", context_lines: int = 5) -> str:
    \"\"\"
    Read contents of a stored evidence file.
    
    If query is provided, performs a grep-like search and returns matching lines
    with context (to save context window space). If query is empty, returns the
    first 200 lines and last 200 lines of the file.
    
    Args:
        evidence_hash: The SHA-256 hash prefix (e.g. "abc1234") of the evidence.
        query: Optional string to search for in the evidence file.
        context_lines: Number of lines before/after to include around matches.
    \"\"\"
    from src.memory.pentest_engagement import get_active_engagement, get_evidence_path
    
    eng = get_active_engagement()
    if not eng:
        return "No active engagement."
        
    path = get_evidence_path(eng["id"], evidence_hash)
    if not path:
        return f"Evidence not found matching hash: {evidence_hash}"
        
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            
        if not query:
            if len(lines) <= 400:
                return "".join(lines)
            return "".join(lines[:200]) + "\\n\\n... [CONTENT TRUNCATED] ...\\n\\n" + "".join(lines[-200:])
            
        # Grep-like search
        query_lower = query.lower()
        matches = []
        for i, line in enumerate(lines):
            if query_lower in line.lower():
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                
                match_block = []
                for j in range(start, end):
                    prefix = ">> " if j == i else "   "
                    match_block.append(f"{j+1:04d}: {prefix}{lines[j].rstrip()}")
                matches.append("\\n".join(match_block))
                
        if not matches:
            return f"No matches found for '{query}' in evidence {evidence_hash[:8]}..."
            
        # Deduplicate overlapping blocks by just returning top matches if too many
        if len(matches) > 20:
            matches = matches[:20]
            matches.append("... [TOO MANY MATCHES - TRUNCATED TO FIRST 20] ...")
            
        return f"Search results for '{query}':\\n\\n" + "\\n---\\n".join(matches)
        
    except Exception as e:
        return f"Error reading evidence: {e}"
"""

content = content.replace("def _guess_mime", read_evidence_func + "\n\ndef _guess_mime")
content = content.replace(
    "    evidence_list,\n    engagement_report,",
    "    evidence_list,\n    read_evidence,\n    engagement_report,",
)

with open("src/tools/pentest_tools.py", "w") as f:
    f.write(content)
