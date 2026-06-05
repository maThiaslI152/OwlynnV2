def _web_search_tool_output_has_results(content: str) -> bool:
    """True when web_search returned normal hit listings (not structured failure)."""
    c = content or ""
    if "Unable to retrieve online results" in c:
        return False
    if c.startswith("[web_search]") and ("Error" in c or "Unable" in c):
        return False
    if "blocked_by_captcha" in c:
        return False
    return ("🔍" in c or "search results for" in c) and "URL:" in c
