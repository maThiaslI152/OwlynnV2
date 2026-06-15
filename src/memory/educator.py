"""Study/educator memory helpers — misconception and mastery atoms."""

from __future__ import annotations

import re

STUDY_STRUGGLE_PREFIX = "[STUDY_STRUGGLE]"

_STUDY_KEYWORDS = (
    "study",
    "quiz",
    "exam prep",
    "exam",
    "learn",
    "chapter",
    "digital literacy",
    "course",
    "lecture",
    "tutorial",
    "teach me",
    "help me learn",
)

_CORRECTION_PATTERNS = (
    re.compile(r"\b(was|is)\s+wrong\b", re.I),
    re.compile(r"\byou'?re?\s+wrong\b", re.I),
    re.compile(r"\bincorrect\b", re.I),
    re.compile(r"\bmisunderstand\b", re.I),
    re.compile(r"\bcorrect\s+your\s+answer\b", re.I),
    re.compile(r"\bplease\s+correct\b", re.I),
    re.compile(r"\bemphasizes\b", re.I),
)

_MASTERY_PATTERNS = (
    re.compile(r"\bi\s+finally\s+understand\b", re.I),
    re.compile(r"\bnow\s+i\s+understand\b", re.I),
    re.compile(r"\bi\s+get\s+it\b", re.I),
    re.compile(r"\bmakes\s+sense\s+now\b", re.I),
    re.compile(r"\bi\s+think\s+i\s+understand\b", re.I),
)


def is_study_correction(human: str) -> bool:
    """True when the user is correcting a prior explanation."""
    text = human.strip()
    if not text:
        return False
    return any(p.search(text) for p in _CORRECTION_PATTERNS)


def is_study_mastery(human: str) -> bool:
    """True when the user signals they now understand the topic."""
    text = human.strip()
    if not text:
        return False
    return any(p.search(text) for p in _MASTERY_PATTERNS)


_STRUGGLE_RECALL_PATTERNS = (
    re.compile(r"\bwhat\s+did\s+i\s+struggle\b", re.I),
    re.compile(r"\bwhat\s+was\s+(hard|difficult|challenging)\b", re.I),
    re.compile(r"\bwhat\s+.*\bstruggle\s+with\b", re.I),
    re.compile(r"\bwhere\s+did\s+i\s+get\s+confused\b", re.I),
    re.compile(r"\bwhat\s+.*\bmisconception\b", re.I),
)


def is_struggle_recall_query(user_text: str) -> bool:
    """True when the user asks to recall prior study difficulties."""
    text = user_text.strip()
    if not text:
        return False
    return any(p.search(text) for p in _STRUGGLE_RECALL_PATTERNS)


def study_struggle_search_queries(user_text: str) -> list[str]:
    """Extra Mem0 queries to surface misconception atoms for struggle recall."""
    queries = [
        f"{STUDY_STRUGGLE_PREFIX} misconception struggle corrected",
        "study misconception user struggled corrected",
        user_text.strip(),
    ]
    topic = re.search(r"digital literacy|chapter\s+\d+", user_text, re.I)
    if topic:
        queries.insert(0, f"{STUDY_STRUGGLE_PREFIX} {topic.group(0)}")
    return queries


def _extract_correction_topic(human: str) -> str:
    topic_match = re.search(
        r"(?:explanation of|about|regarding)\s+([^—\-.]+)",
        human,
        re.I,
    )
    return topic_match.group(1).strip() if topic_match else "study topic"


def _extract_correction_focus(human: str) -> str:
    """Pull the user's stated correction (e.g. what the PDF actually emphasizes)."""
    focus_match = re.search(
        r"(?:pdf|chapter|textbook)\s+(?:emphasizes?|says?|focuses? on)\s+(.+?)(?:\.|$)",
        human,
        re.I,
    )
    if focus_match:
        return focus_match.group(1).strip()[:200]
    dash_match = re.search(r"—\s*(.+?)(?:\.|$)", human)
    if dash_match:
        return dash_match.group(1).strip()[:200]
    return ""


def build_misconception_atom(human: str, ai: str) -> str:
    """Build a dense LTM atom capturing a study struggle/correction."""
    topic = _extract_correction_topic(human)
    focus = _extract_correction_focus(human)
    human_snip = human.strip()[:300]
    focus_part = f" Correction focus: {focus}." if focus else ""
    return (
        f"{STUDY_STRUGGLE_PREFIX} {topic}: User struggled with this topic and "
        f"corrected a misconception.{focus_part} "
        f"User criticism: {human_snip}"
    )


def build_mastery_atom(human: str) -> str:
    """Build a dense LTM atom when the user confirms understanding."""
    topic_match = re.search(
        r"(?:understand|get)\s+(.+?)(?:\s+now|\.|$)",
        human,
        re.I,
    )
    topic = topic_match.group(1).strip() if topic_match else human.strip()[:100]
    return (
        f"[STUDY_MASTERY] {topic}: User achieved mastery after prior struggle. "
        f"User confirmation: {human.strip()[:200]}"
    )


def is_study_memory_item(item: object) -> bool:
    """True if a Mem0 result is a study struggle or mastery atom."""
    if not isinstance(item, dict):
        return False
    text = (item.get("memory") or item.get("text") or "").lower()
    meta = item.get("metadata") or {}
    tags = meta.get("tags") or []
    if STUDY_STRUGGLE_PREFIX.lower() in text or "[study_mastery]" in text:
        return True
    if meta.get("type") == "study_atom":
        return True
    if "misconception" in tags or "mastery" in tags:
        return True
    return "misconception" in text and "struggled" in text


def prioritize_study_memories(results: list) -> list:
    """Move study struggle/mastery atoms to the front, dedupe by memory text."""
    study: list = []
    other: list = []
    seen: set[str] = set()
    for item in results:
        text = ""
        if isinstance(item, dict):
            text = str(item.get("memory") or item.get("text") or "")
        key = text[:120]
        if key in seen:
            continue
        seen.add(key)
        if is_study_memory_item(item):
            study.append(item)
        else:
            other.append(item)
    return study + other


def fetch_study_struggle_memories(
    memory: object, mem0_uid: str, user_text: str
) -> list:
    """Run targeted Mem0 searches for study struggle recall."""
    merged: list = []
    seen: set[str] = set()
    for query in study_struggle_search_queries(user_text):
        try:
            results_dict = memory.search(query, filters={"user_id": mem0_uid}, limit=10)
            batch = (
                results_dict.get("results", [])
                if isinstance(results_dict, dict)
                else results_dict
            )
            for item in batch or []:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("memory") or item.get("text") or "")[:120]
                if key and key not in seen:
                    seen.add(key)
                    merged.append(item)
        except Exception:
            continue
    return prioritize_study_memories(merged)


def resolve_study_scenario(response_style: str | None, user_text: str) -> str | None:
    """Return ``study`` when learning mode or study-related keywords are present."""
    if (response_style or "").strip().lower() == "learning":
        return "study"
    lower = user_text.lower()
    if any(kw in lower for kw in _STUDY_KEYWORDS):
        return "study"
    return None
