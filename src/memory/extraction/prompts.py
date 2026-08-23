"""Custom extraction prompts — structured atoms only, no conversational prose."""

EXTRACTION_SYSTEM = """You extract durable facts from conversation turns for long-term memory.
Output ONLY valid JSON. No markdown fences, no commentary.

Schema:
{
  "atoms": [
    {
      "tier": "L1",
      "format": "jsdoc",
      "content": "/** @fact ... */",
      "tags": ["pentest"],
      "confidence": 0.0-1.0,
      "source": "conversation"
    }
  ]
}

Rules:
- ``format`` must be one of: jsdoc, docstring, json
- ``content`` must be dense structured text (JSDoc, Python docstring, or JSON string)
- Never store greetings, apologies, or filler
- Never include raw API keys, passwords, or emails (they are already redacted)
- If nothing worth storing, return {"atoms": []}
"""

PENTEST_EXTRACTION_USER = """Scenario: penetration testing / security auditing.
Prefer tags: pentest, infra, vuln, scope, credential-policy.
Extract only security-relevant durable facts (targets, scope boundaries, findings, tooling preferences).

Conversation turn:
{turn_text}
"""

RESEARCH_EXTRACTION_USER = """Scenario: research / documentation synthesis.
Prefer tags: research, source, topic, citation.
Extract durable facts the user would want recalled later (definitions, preferences, conclusions).

Conversation turn:
{turn_text}
"""

STUDY_EXTRACTION_USER = """Scenario: study / educator tutoring.
Prefer tags: study, misconception, mastery, struggle, topic.
Extract durable facts about what the user struggled with, corrected misconceptions,
topics they mastered, and course/chapter context they would want recalled later.

Conversation turn:
{turn_text}
"""

DEFAULT_EXTRACTION_USER = """Extract durable user-specific facts from this turn.

Conversation turn:
{turn_text}
"""


def build_extraction_messages(
    turn_text: str, scenario_id: str | None = None
) -> list[dict[str, str]]:
    if scenario_id == "pentest":
        user = PENTEST_EXTRACTION_USER.format(turn_text=turn_text)
    elif scenario_id == "research":
        user = RESEARCH_EXTRACTION_USER.format(turn_text=turn_text)
    elif scenario_id == "study":
        user = STUDY_EXTRACTION_USER.format(turn_text=turn_text)
    else:
        user = DEFAULT_EXTRACTION_USER.format(turn_text=turn_text)
    return [
        {"role": "system", "content": EXTRACTION_SYSTEM},
        {"role": "user", "content": user},
    ]


SKILL_EXTRACTION_SYSTEM = """You extract procedural skills, tool execution recipes, and user corrections from conversation turns for skill synthesis.
Output ONLY valid JSON. No markdown fences, no commentary.

Schema:
{
  "has_learning": true,
  "action": "patch_active" | "update_umbrella" | "add_support_file" | "create_skill" | "none",
  "target_skill": "skill_name_or_umbrella",
  "folder_type": "references" | "templates" | "scripts" | "main",
  "relative_path": "references/topic_notes.md",
  "content": "detailed markdown or script content...",
  "rationale": "Brief rationale for why this skill update was learned",
  "category": "general" | "research" | "writing" | "productivity" | "data" | "communication"
}

Signals to look for:
1. User corrected style, format, verbosity, tool selection, or workflow sequence.
2. Successful non-trivial troubleshooting, exploit, or data processing recipes.
3. Repetitive command patterns that warrant a reusable script or template.
If no procedural learning is present, return {"has_learning": false, "action": "none"}.
"""

SKILL_EXTRACTION_USER = """Scenario: {scenario_id}

Conversation turn:
{turn_text}
"""


def build_skill_extraction_messages(
    turn_text: str, scenario_id: str | None = None
) -> list[dict[str, str]]:
    user = SKILL_EXTRACTION_USER.format(
        scenario_id=scenario_id or "general",
        turn_text=turn_text,
    )
    return [
        {"role": "system", "content": SKILL_EXTRACTION_SYSTEM},
        {"role": "user", "content": user},
    ]
