"""L2/L3 scenario markdown loader (pentest + research)."""

from __future__ import annotations

import re
from pathlib import Path

_SCENARIOS_ROOT = Path(__file__).resolve().parents[2] / "scenarios"

_PENTEST_HINTS = (
    "nmap",
    "sqlmap",
    "burp",
    "metasploit",
    "cve-",
    "payload",
    "enumeration",
    "privesc",
    "lateral movement",
    "pentest",
    "penetration test",
    "kali",
    "engagement scope",
    "exploit",
    "vulnerability",
)

_RESEARCH_HINTS = (
    "summarize",
    "research",
    "compare",
    "documentation",
    "whitepaper",
    "paper",
    "cite",
    "sources",
    "how does",
    "explain",
    "literature",
)


def detect_scenario_id(user_text: str) -> str | None:
    """Heuristic scenario classification for router fallback."""
    lower = user_text.lower()
    pentest_score = sum(1 for h in _PENTEST_HINTS if h in lower)
    research_score = sum(1 for h in _RESEARCH_HINTS if h in lower)
    if pentest_score >= 2 or (pentest_score >= 1 and research_score == 0):
        return "pentest"
    if research_score >= 2:
        return "research"
    if pentest_score == 1:
        return "pentest"
    if research_score == 1:
        return "research"
    return None


def load_scenario_markdown(scenario_id: str | None) -> tuple[str, str]:
    """Load (playbook L2, constraints L3) for a scenario id."""
    if not scenario_id:
        return ("", "")
    base = _SCENARIOS_ROOT / scenario_id
    playbook = _read_md(base / "playbook.md")
    constraints = _read_md(base / "constraints.md")
    return playbook, constraints


def format_scenario_context(scenario_id: str | None) -> str:
    """Merge L2+L3 into a single injectable block."""
    playbook, constraints = load_scenario_markdown(scenario_id)
    if not playbook and not constraints:
        return ""
    parts = []
    if playbook:
        parts.append(f"## Scenario playbook ({scenario_id})\n{playbook}")
    if constraints:
        parts.append(f"## Scenario constraints ({scenario_id})\n{constraints}")
    return "\n\n".join(parts)


def _read_md(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()
