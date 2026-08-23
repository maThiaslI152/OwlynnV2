"""
Skills System — Reusable prompt templates loaded from skills/ folder.
Mirrors Cowork's Skills: domain-specific knowledge that triggers on keyword match.

Each skill is a markdown file in PROJECT_ROOT/skills/ with front-matter:
---
name: Morning Briefing
triggers: [briefing, morning, daily summary]
description: Creates a daily briefing from calendar/email/tasks
---
<prompt body>
"""

import json
import logging
import re
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.tools import tool

from src.config.config_loader import config as _app_config
from src.config.settings import PROJECT_ROOT

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False

SKILLS_DIR = PROJECT_ROOT / "skills"

ALLOWED_CATEGORIES = {
    "research",
    "writing",
    "productivity",
    "data",
    "communication",
    "general",
}


@dataclass
class SkillParam:
    """A single named parameter declared by a skill."""

    name: str
    description: str
    required: bool = True
    default: str | None = None


@dataclass
class SkillDefinition:
    """Structured representation of a parsed skill template."""

    file: str
    name: str
    triggers: list[str]
    description: str
    prompt: str
    category: str = "general"
    params: list[SkillParam] = field(default_factory=list)
    chain_compatible: bool = True
    version: str = "1.0"
    tools_used: list[str] = field(default_factory=list)
    is_package: bool = False
    package_dir: str | None = None
    support_files: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("SkillDefinition name must be non-empty")
        if not self.triggers:
            raise ValueError("SkillDefinition triggers must contain at least one entry")
        if not self.prompt or not self.prompt.strip():
            raise ValueError("SkillDefinition prompt must be non-empty")
        if self.category not in ALLOWED_CATEGORIES:
            raise ValueError(
                f"Invalid category '{self.category}'. Must be one of: {', '.join(sorted(ALLOWED_CATEGORIES))}"
            )
        param_names = [p.name for p in self.params]
        if len(param_names) != len(set(param_names)):
            raise ValueError("SkillDefinition param names must be unique")


@dataclass
class MatchResult:
    """Result of a skill match operation with ambiguity information.

    Attributes:
        is_ambiguous: True when the match is uncertain and HITL should be triggered.
        top_match: The highest-scoring skill, or None if no skills matched.
        candidate_skills: Up to 5 best matches for display in a choice popup.
        ambiguity_reason: Human-readable description of why the match is ambiguous.
        best_score: The combined score of the top match (0.0-1.0).
    """

    is_ambiguous: bool
    top_match: SkillDefinition | None = None
    candidate_skills: list[tuple[SkillDefinition, float]] = field(default_factory=list)
    ambiguity_reason: str = ""
    best_score: float = 0.0


def _parse_front_matter(text: str) -> tuple[dict, str]:
    """Parse YAML-like front matter from a markdown skill file.

    Handles both v1.0 simple fields and v2.0 structured fields including
    multi-line ``params`` blocks with sub-fields (name, description, required,
    default) and boolean values for ``chain_compatible``.
    """
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not m:
        return {}, text
    meta_block, body = m.group(1), m.group(2)
    meta: dict = {}
    lines = meta_block.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            i += 1
            continue
        key, val = stripped.split(":", 1)
        key = key.strip()
        val = val.strip()

        # Multi-line list block (e.g. params with structured entries)
        if val == "" and key == "params":
            param_list: list[dict] = []
            i += 1
            current_param: dict | None = None
            while i < len(lines):
                pline = lines[i]
                # Stop if we hit a top-level key (non-indented, has colon)
                if pline and not pline[0].isspace() and ":" in pline:
                    break
                pline_stripped = pline.strip()
                if not pline_stripped:
                    i += 1
                    continue
                if pline_stripped.startswith("- "):
                    # New list item — could be "- name: value" or just "- value"
                    item_content = pline_stripped[2:].strip()
                    if ":" in item_content:
                        current_param = {}
                        sub_key, sub_val = item_content.split(":", 1)
                        sub_key = sub_key.strip()
                        sub_val = sub_val.strip()
                        current_param[sub_key] = sub_val
                    else:
                        # Simple list item inside params (unlikely but handle)
                        current_param = {"name": item_content}
                    param_list.append(current_param)
                elif current_param is not None and ":" in pline_stripped:
                    # Continuation sub-field of current param
                    sub_key, sub_val = pline_stripped.split(":", 1)
                    sub_key = sub_key.strip()
                    sub_val = sub_val.strip()
                    current_param[sub_key] = sub_val
                i += 1
            meta[key] = param_list
            continue  # don't increment i again

        # Inline list syntax [item1, item2]
        if val.startswith("[") and val.endswith("]"):
            val = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
        # Boolean coercion for chain_compatible
        elif key == "chain_compatible":
            val = val.strip("'\"").lower() not in ("false", "no", "0")
        else:
            # Strip surrounding quotes from plain string values
            if (val.startswith('"') and val.endswith('"')) or (
                val.startswith("'") and val.endswith("'")
            ):
                val = val[1:-1]
        meta[key] = val
        i += 1
    return meta, body.strip()


def _parse_skill_file(
    text: str, filename: str, package_dir: Path | None = None
) -> SkillDefinition:
    """Parse a skill markdown file and return a fully-populated SkillDefinition.

    Applies v2.0 defaults for any missing fields so that v1.0 skill files
    remain backward-compatible.
    """
    meta, body = _parse_front_matter(text)

    # Build SkillParam list from parsed params dicts
    raw_params = meta.get("params", [])
    params: list[SkillParam] = []
    if isinstance(raw_params, list):
        for entry in raw_params:
            if isinstance(entry, dict):
                req_raw = entry.get("required", "true")
                if isinstance(req_raw, str):
                    required = req_raw.lower() not in ("false", "no", "0")
                else:
                    required = bool(req_raw)
                params.append(
                    SkillParam(
                        name=entry.get("name", ""),
                        description=entry.get("description", ""),
                        required=required,
                        default=entry.get("default"),
                    )
                )

    # Normalise tools_used to a list
    tools_used = meta.get("tools_used", [])
    if isinstance(tools_used, str):
        tools_used = [t.strip() for t in tools_used.split(",") if t.strip()]

    default_name = package_dir.name if package_dir else Path(filename).stem
    name = meta.get("name", default_name)

    # Normalise triggers to a list
    triggers = meta.get("triggers", [])
    if isinstance(triggers, str):
        triggers = [triggers]
    if not triggers and (package_dir is not None or filename.endswith("SKILL.md")):
        triggers = [name]

    # chain_compatible
    chain_compatible = meta.get("chain_compatible", True)
    if isinstance(chain_compatible, str):
        chain_compatible = chain_compatible.lower() not in ("false", "no", "0")

    is_pkg = package_dir is not None
    support_files: dict[str, str] = {}
    if package_dir and package_dir.is_dir():
        for sub_folder in ("references", "templates", "scripts", "assets"):
            sdir = package_dir / sub_folder
            if sdir.is_dir():
                for sfile in sorted(sdir.rglob("*")):
                    if sfile.is_file():
                        rel = str(sfile.relative_to(package_dir))
                        support_files[rel] = str(sfile)

    return SkillDefinition(
        file=filename,
        name=name,
        triggers=triggers,
        description=meta.get("description", ""),
        prompt=body,
        category=meta.get("category", "general"),
        params=params,
        chain_compatible=chain_compatible,
        version=meta.get("version", "1.0"),
        tools_used=tools_used,
        is_package=is_pkg,
        package_dir=str(package_dir) if package_dir else None,
        support_files=support_files,
    )


logger = logging.getLogger(__name__)


class SkillLoader:
    """Loads, parses, and caches skill definitions from ``skills/`` and ``.agents/skills/``."""

    def __init__(
        self, skills_dir: Path, secondary_dirs: list[Path] | None = None
    ) -> None:
        self._skills_dir = skills_dir
        self._secondary_dirs = secondary_dirs if secondary_dirs is not None else []
        self._cache: dict[str, SkillDefinition] = {}
        self._last_scan: float = 0.0
        self._cache_ttl: float = 30.0

    def _scan_dir(self, directory: Path) -> list[SkillDefinition]:
        if not directory.exists():
            return []
        found: list[SkillDefinition] = []

        # 1. Flat .md files
        for f in sorted(directory.glob("*.md")):
            if f.name == "SKILL.md":
                continue
            try:
                text = f.read_text(encoding="utf-8")
                skill = _parse_skill_file(text, f.name)
                found.append(skill)
            except Exception as exc:
                logger.warning("Skipping skill file %s: %s", f.name, exc)

        # 2. Package directories with SKILL.md
        for skill_md in sorted(directory.glob("**/SKILL.md")):
            pkg_dir = skill_md.parent
            if pkg_dir.name in (
                "references",
                "templates",
                "scripts",
                "assets",
                ".archive",
            ):
                continue
            try:
                text = skill_md.read_text(encoding="utf-8")
                rel_file = str(skill_md.relative_to(directory))
                skill = _parse_skill_file(text, rel_file, package_dir=pkg_dir)
                found.append(skill)
            except Exception as exc:
                logger.warning("Skipping skill package %s: %s", pkg_dir.name, exc)

        return found

    def load_all(self) -> list[SkillDefinition]:
        """Parse all skill definitions; return cached list if within TTL."""
        if self._cache and time.time() - self._last_scan < self._cache_ttl:
            return list(self._cache.values())

        self._skills_dir.mkdir(parents=True, exist_ok=True)
        self._cache.clear()

        # Primary skills dir
        for s in self._scan_dir(self._skills_dir):
            self._cache[s.file] = s

        # Secondary directories
        for sdir in self._secondary_dirs:
            for s in self._scan_dir(sdir):
                if s.file not in self._cache and s.name not in [
                    x.name for x in self._cache.values()
                ]:
                    self._cache[s.file] = s

        self._last_scan = time.time()
        return list(self._cache.values())

    def load_one(self, filename: str) -> SkillDefinition | None:
        """Parse a single skill file and return its definition, or ``None``."""
        # Try direct file in skills_dir
        path = self._skills_dir / filename
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8")
                skill = _parse_skill_file(text, filename)
                self._cache[filename] = skill
                return skill
            except Exception as exc:
                logger.warning("Skipping skill file %s: %s", filename, exc)
                return None

        # Try package dir
        if path.is_dir() and (path / "SKILL.md").is_file():
            try:
                text = (path / "SKILL.md").read_text(encoding="utf-8")
                skill = _parse_skill_file(
                    text, f"{filename}/SKILL.md", package_dir=path
                )
                self._cache[filename] = skill
                return skill
            except Exception as exc:
                logger.warning("Skipping skill package %s: %s", filename, exc)
                return None

        # Secondary dirs
        for sdir in self._secondary_dirs:
            spath = sdir / filename
            if spath.is_file():
                try:
                    text = spath.read_text(encoding="utf-8")
                    skill = _parse_skill_file(text, filename)
                    self._cache[filename] = skill
                    return skill
                except Exception:
                    pass
            elif spath.is_dir() and (spath / "SKILL.md").is_file():
                try:
                    text = (spath / "SKILL.md").read_text(encoding="utf-8")
                    skill = _parse_skill_file(
                        text, f"{filename}/SKILL.md", package_dir=spath
                    )
                    self._cache[filename] = skill
                    return skill
                except Exception:
                    pass

        return None

    def invalidate_cache(self) -> None:
        """Clear the cache so the next ``load_all`` re-reads from disk."""
        self._cache.clear()
        self._last_scan = 0.0

    def get_by_name(self, name: str) -> SkillDefinition | None:
        """Lookup a cached skill by name (case-insensitive)."""
        if not self._cache:
            self.load_all()
        name_lower = name.lower()
        for skill in self._cache.values():
            if skill.name.lower() == name_lower:
                return skill
        return None

    def get_by_category(self, category: str) -> list[SkillDefinition]:
        """Return all cached skills belonging to *category*."""
        if not self._cache:
            self.load_all()
        return [s for s in self._cache.values() if s.category == category]


_default_loader = SkillLoader(
    SKILLS_DIR, secondary_dirs=[PROJECT_ROOT / ".agents" / "skills"]
)


class SkillMatcher:
    """Hybrid matching engine combining keyword triggers with TF-IDF similarity scoring."""

    def __init__(self, loader: SkillLoader) -> None:
        self._loader = loader
        self._tfidf_matrix = None
        self._vectorizer = None
        self._skill_names: list[str] = []

    def match(self, query: str, top_k: int = 3) -> list[tuple[SkillDefinition, float]]:
        """Return up to *top_k* skills whose combined score meets the threshold.

        Combined score = 0.6 * keyword + 0.4 * semantic.
        Results are sorted by score descending.
        """
        KEYWORD_WEIGHT = 0.6
        SEMANTIC_WEIGHT = 0.4
        THRESHOLD = 0.3

        skills = self._loader.load_all()
        if not skills:
            return []

        # Build a name→skill lookup for semantic results
        skill_by_name: dict[str, SkillDefinition] = {s.file: s for s in skills}

        # Keyword scores
        kw_scores: dict[str, float] = {}
        for skill in skills:
            kw_scores[skill.file] = self._keyword_score(query, skill)

        # Semantic scores (TF-IDF or empty if sklearn unavailable)
        sem_scores: dict[str, float] = {}
        if _HAS_SKLEARN:
            for name, score in self._semantic_score(query):
                sem_scores[name] = score

        # Combine
        combined: list[tuple[SkillDefinition, float]] = []
        for skill in skills:
            kw = kw_scores.get(skill.file, 0.0)
            sem = sem_scores.get(skill.file, 0.0)
            final = KEYWORD_WEIGHT * kw + SEMANTIC_WEIGHT * sem
            # Clamp to [0.0, 1.0]
            final = max(0.0, min(1.0, final))
            if final >= THRESHOLD:
                combined.append((skill, final))

        combined.sort(key=lambda x: x[1], reverse=True)
        return combined[:top_k]

    def match_best(self, query: str, threshold: float = 0.3) -> SkillDefinition | None:
        """Return the single best match above *threshold*, or ``None``."""
        results = self.match(query, top_k=1)
        if results and results[0][1] >= threshold:
            return results[0][0]
        return None

    # ── Thresholds for ambiguity detection ──────────────────────────────
    LOW_CONFIDENCE_THRESHOLD = float(
        _app_config.get("routing.skill.low_confidence_threshold", 0.5)
    )
    TIE_MARGIN = float(_app_config.get("routing.skill.tie_margin", 0.15))
    TIE_MIN_TOP_SCORE = float(_app_config.get("routing.skill.tie_min_top_score", 0.3))
    VAGUE_WORD_COUNT = int(_app_config.get("routing.skill.vague_word_count", 3))

    # Weak intent-signalling keywords — if none of these appear, the
    # query is likely too vague to match skills confidently.
    _INTENT_KEYWORDS: set[str] = {
        "research",
        "investigate",
        "analyze",
        "explain",
        "summarize",
        "write",
        "create",
        "build",
        "generate",
        "refactor",
        "review",
        "check",
        "audit",
        "visualize",
        "chart",
        "graph",
        "plot",
        "email",
        "draft",
        "compose",
        "report",
        "briefing",
        "brainstorm",
        "suggest",
        "idea",
        "plan",
        "todo",
        "task",
        "code",
        "document",
        "data",
        "compare",
        "rewrite",
        "translate",
        "scan",
        "search",
        "look",
        "find",
        "meeting",
        "note",
        "presentation",
        "slide",
        "verify",
        "fact",
    }

    def match_with_confidence(self, query: str, top_k: int = 5) -> MatchResult:
        """Run skill matching with ambiguity detection for HITL gating.

        Returns a :class:`MatchResult` with:
        - ``is_ambiguous``: True when the match is uncertain (three-signal check).
        - ``candidate_skills``: Up to *top_k* best matches for display as choices.
        - ``ambiguity_reason``: Human-readable explanation when ambiguous.
        - ``top_match`` / ``best_score``: Best match and its score.

        Three ambiguity signals:

        **Signal A — Low Confidence**: Best combined score < ``LOW_CONFIDENCE_THRESHOLD`` (0.5).

        **Signal B — Multi-Tie**: Two or more skills within ``TIE_MARGIN`` (0.15)
        of each other AND top score > ``TIE_MIN_TOP_SCORE`` (0.3).

        **Signal C — Vague Query**: Query has fewer than ``VAGUE_WORD_COUNT`` (3)
        words OR contains no recognised intent keywords.
        """
        results = self.match(query, top_k=top_k)

        # ── Signal C: vague query detection ──────────────────────────
        words = query.strip().split()
        query_lower = query.lower()
        has_intent_keywords = any(kw in query_lower for kw in self._INTENT_KEYWORDS)
        vague_query = len(words) < self.VAGUE_WORD_COUNT and not has_intent_keywords

        if not results:
            # No skills matched at all
            if vague_query:
                reason = (
                    f"Your query is very short ({len(words)} words) with no clear intent. "
                    "Try adding more detail about what you need."
                )
                return MatchResult(
                    is_ambiguous=True,
                    candidate_skills=[],
                    ambiguity_reason=reason,
                )
            # Query has clear intent but no specific skill matches —
            # route directly without HITL interruption.
            return MatchResult(
                is_ambiguous=False,
                candidate_skills=[],
                ambiguity_reason="",
            )

        best = results[0]
        best_score = best[1]

        # ── Signal A: low confidence ─────────────────────────────────
        low_confidence = best_score < self.LOW_CONFIDENCE_THRESHOLD

        # ── Signal B: multi-tie ──────────────────────────────────────
        multi_tie = False
        if len(results) >= 2 and best_score >= self.TIE_MIN_TOP_SCORE:
            second_score = results[1][1]
            if (best_score - second_score) <= self.TIE_MARGIN:
                multi_tie = True

        # ── Build ambiguity reason ───────────────────────────────────
        reasons: list[str] = []
        if low_confidence:
            reasons.append(
                f"Best match '{best[0].name}' has low confidence ({best_score:.0%})"
            )
        if multi_tie:
            tied_names = [
                r[0].name for r in results if (best_score - r[1]) <= self.TIE_MARGIN
            ]
            reasons.append(
                f"Multiple skills are close matches: {', '.join(tied_names[:3])}"
            )
        if vague_query:
            reasons.append(f"Query is vague ({len(words)} words, no strong intent)")
        if not reasons and not vague_query:
            reasons.append("Query is ambiguous — unable to determine the best match")

        is_ambiguous = low_confidence or multi_tie or vague_query

        return MatchResult(
            is_ambiguous=is_ambiguous,
            top_match=best[0],
            candidate_skills=results[:top_k],
            ambiguity_reason="; ".join(reasons) if is_ambiguous else "",
            best_score=best_score,
        )

    def _keyword_score(self, query: str, skill: SkillDefinition) -> float:
        """Score a skill against *query* using trigger substring / token overlap.

        - If any trigger is an exact substring of the query → 1.0
        - Otherwise, compute token overlap ratio scaled by 0.5
        - No overlap → 0.0
        """
        query_lower = query.lower()
        query_tokens = set(query_lower.split())

        # Exact substring check
        for trigger in skill.triggers:
            if trigger.lower() in query_lower:
                return 1.0

        # Partial token overlap
        trigger_tokens: set[str] = set()
        for trigger in skill.triggers:
            trigger_tokens.update(trigger.lower().split())

        overlap = query_tokens & trigger_tokens
        if overlap:
            return 0.5 * len(overlap) / max(len(trigger_tokens), 1)

        return 0.0

    def _semantic_score(self, query: str) -> list[tuple[str, float]]:
        """Compute TF-IDF cosine similarity of *query* against all loaded skills.

        Returns a list of ``(skill_file_name, similarity)`` pairs.
        Falls back to an empty list when scikit-learn is unavailable.
        """
        if not _HAS_SKLEARN:
            return []

        self._rebuild_index()

        if self._tfidf_matrix is None or self._vectorizer is None:
            return []

        query_vec = self._vectorizer.transform([query])
        similarities = cosine_similarity(query_vec, self._tfidf_matrix).flatten()

        results: list[tuple[str, float]] = []
        for i, name in enumerate(self._skill_names):
            results.append((name, float(similarities[i])))
        return results

    def _rebuild_index(self) -> None:
        """Rebuild the TF-IDF matrix from currently loaded skills."""
        if not _HAS_SKLEARN:
            return

        skills = self._loader.load_all()
        if not skills:
            self._tfidf_matrix = None
            self._vectorizer = None
            self._skill_names = []
            return

        self._skill_names = [s.file for s in skills]
        corpus = [f"{s.name} {s.description} {' '.join(s.triggers)}" for s in skills]

        self._vectorizer = TfidfVectorizer()
        self._tfidf_matrix = self._vectorizer.fit_transform(corpus)


class ContextInjector:
    """Renders skill prompts with context, parameters, and chain state."""

    def inject(
        self,
        skill: SkillDefinition,
        context: str,
        params: dict[str, str] | None = None,
        chain_state: dict | None = None,
    ) -> str:
        """Render a skill prompt with context, parameters, and chain state.

        1. Validate and fill params (required check + defaults).
        2. Replace ``{context}`` and ``{input}`` placeholders.
        3. Replace ``{param_name}`` placeholders.
        4. Prepend chain header if *chain_state* has previous steps.
        """
        params = self._validate_params(skill, params or {})

        prompt = skill.prompt

        # Replace standard placeholders
        prompt = prompt.replace("{context}", context)
        prompt = prompt.replace("{input}", context)

        # Replace named param placeholders
        for key, value in params.items():
            prompt = prompt.replace(f"{{{key}}}", value)

        # Inject chain context
        if chain_state and chain_state.get("previous_steps"):
            prompt = self._apply_chain_context(prompt, chain_state)

        return prompt

    def _validate_params(self, skill: SkillDefinition, params: dict) -> dict:
        """Validate required params are present and apply defaults for optional ones.

        Raises :class:`ValueError` for any missing required parameter.
        Returns the completed params dict.
        """
        completed = dict(params)
        for sp in skill.params:
            if sp.required and sp.name not in completed:
                raise ValueError(
                    f"Missing required parameter '{sp.name}': {sp.description}"
                )
            if sp.name not in completed and sp.default is not None:
                completed[sp.name] = sp.default
        return completed

    def _apply_chain_context(self, prompt: str, chain_state: dict) -> str:
        """Prepend a chain header with step number, total, and previous step names."""
        step_num = chain_state.get("current_step", 1)
        total = chain_state.get("step_count", 1)
        prev_names = ", ".join(chain_state.get("previous_steps", []))
        chain_header = (
            f"[Chain Step {step_num}/{total} — Previous: {prev_names}]\n"
            f"Use the output from the previous step(s) as input for this step.\n\n"
        )
        return chain_header + prompt


_default_injector = ContextInjector()


@dataclass
class ChainStep:
    """A single step in a skill chain."""

    skill_name: str
    params: dict[str, str] = field(default_factory=dict)
    context_override: str | None = None


@dataclass
class ChainResult:
    """Result of building a skill chain pipeline."""

    steps: list[str]  # rendered prompts per step
    instructions: str  # overall chain instructions for the LLM


class ChainPipeline:
    """Orchestrates multi-skill workflows by composing skill prompts sequentially."""

    MAX_CHAIN_LENGTH = 5

    def __init__(self, loader: SkillLoader, injector: ContextInjector) -> None:
        self._loader = loader
        self._injector = injector

    def build(self, steps: list[str | ChainStep], context: str) -> ChainResult:
        """Build a multi-skill chain by composing prompts sequentially.

        Args:
            steps: Skill names (str) or :class:`ChainStep` objects.
            context: Base context string passed to each step.

        Returns:
            A :class:`ChainResult` with rendered prompts and LLM instructions.

        Raises:
            ValueError: If the chain exceeds 5 steps, any skill is not found,
                or any skill is not chain-compatible.
        """
        if len(steps) > self.MAX_CHAIN_LENGTH:
            raise ValueError(f"Chain too long: {len(steps)} > {self.MAX_CHAIN_LENGTH}")

        # Normalize string steps to ChainStep objects
        normalized: list[ChainStep] = []
        for step in steps:
            if isinstance(step, str):
                normalized.append(ChainStep(skill_name=step))
            else:
                normalized.append(step)

        # Validate all skills exist and are chain-compatible (before rendering)
        errors: list[str] = []
        resolved: list[SkillDefinition] = []
        for cs in normalized:
            skill = self._loader.get_by_name(cs.skill_name)
            if skill is None:
                errors.append(f"Skill not found: {cs.skill_name}")
            elif not skill.chain_compatible:
                errors.append(f"Skill not chain-compatible: {cs.skill_name}")
            else:
                resolved.append(skill)

        if errors:
            raise ValueError("; ".join(errors))

        # Build rendered prompts
        rendered_steps: list[str] = []
        chain_state: dict = {
            "step_count": len(normalized),
            "previous_steps": [],
        }

        for i, (cs, skill) in enumerate(zip(normalized, resolved)):
            chain_state["current_step"] = i + 1
            step_context = cs.context_override or context

            rendered = self._injector.inject(
                skill=skill,
                context=step_context,
                params=cs.params,
                chain_state=chain_state if i > 0 else None,
            )
            rendered_steps.append(rendered)
            chain_state["previous_steps"].append(skill.name)

        # Generate chain instructions
        step_names = [s.name for s in resolved]
        instructions = (
            f"[Skill Chain: {len(step_names)} steps]\n"
            f"Execute these skills in order, passing output from each step as context to the next:\n"
        )
        for i, name in enumerate(step_names, 1):
            instructions += f"  Step {i}: {name}\n"
        instructions += "\nComplete each step fully before moving to the next."

        return ChainResult(steps=rendered_steps, instructions=instructions)

    def validate_chain(self, steps: list[str]) -> list[str]:
        """Validate a chain of skill names without rendering.

        Returns:
            A list of error strings. Empty if the chain is valid.
        """
        errors: list[str] = []
        if len(steps) > self.MAX_CHAIN_LENGTH:
            errors.append(f"Chain too long: {len(steps)} > {self.MAX_CHAIN_LENGTH}")
        for name in steps:
            skill = self._loader.get_by_name(name)
            if skill is None:
                errors.append(f"Skill not found: {name}")
            elif not skill.chain_compatible:
                errors.append(f"Skill not chain-compatible: {name}")
        return errors


def load_all_skills() -> list[dict]:
    """Load all skill definitions from the skills directory.

    .. deprecated::
        Use ``_default_loader.load_all()`` instead.  This wrapper converts
        :class:`SkillDefinition` objects back to plain dicts for backward
        compatibility.
    """
    warnings.warn(
        "load_all_skills() is deprecated, use SkillLoader.load_all() instead",
        DeprecationWarning,
        stacklevel=2,
    )
    skills = _default_loader.load_all()
    return [
        {
            "file": s.file,
            "name": s.name,
            "triggers": s.triggers,
            "description": s.description,
            "prompt": s.prompt,
        }
        for s in skills
    ]


def find_matching_skill(user_text: str) -> dict | None:
    """Find a skill whose triggers match the user's message.

    .. deprecated::
        Use ``_default_loader.get_by_name()`` or a :class:`SkillMatcher`
        instead.  This wrapper delegates to the default loader and checks
        triggers for backward compatibility.
    """
    warnings.warn(
        "find_matching_skill() is deprecated, use SkillLoader or SkillMatcher instead",
        DeprecationWarning,
        stacklevel=2,
    )
    lower = user_text.lower()
    for skill in _default_loader.load_all():
        triggers = (
            skill.triggers if isinstance(skill.triggers, list) else [skill.triggers]
        )
        for t in triggers:
            if t.lower() in lower:
                return {
                    "file": skill.file,
                    "name": skill.name,
                    "triggers": skill.triggers,
                    "description": skill.description,
                    "prompt": skill.prompt,
                }
    return None


@tool
def list_skills(category: str = "") -> str:
    """Lists available skills, optionally filtered by category.

    Args:
        category: Optional category filter (research, writing, productivity, data, communication, general). Leave empty for all.
    """
    if category:
        skills = _default_loader.get_by_category(category)
        if not skills:
            return f"No skills found in category '{category}'."
        lines = [f"📂 {category}:"]
        for s in skills:
            lines.append(f"  • {s.name}: {s.description}")
        return "\n".join(lines)

    # No category filter — return all skills grouped by category
    skills = _default_loader.load_all()
    if not skills:
        return "No skills found."

    # Group by category
    grouped: dict[str, list[SkillDefinition]] = {}
    for s in skills:
        grouped.setdefault(s.category, []).append(s)

    lines = ["📚 Available Skills:"]
    for cat in sorted(grouped):
        lines.append(f"\n📂 {cat}:")
        for s in grouped[cat]:
            lines.append(f"  • {s.name}: {s.description}")
    return "\n".join(lines)


@tool
def invoke_skill(skill_name: str, context: str = "", params: str = "") -> str:
    """Invokes a named skill with context and optional parameters.

    Args:
        skill_name: Name of the skill to invoke.
        context: Additional context to inject into the skill prompt.
        params: Optional JSON string of key-value parameters (e.g. '{"depth": "deep"}').
    """
    skill = _default_loader.get_by_name(skill_name)
    if not skill:
        all_skills = _default_loader.load_all()
        available = ", ".join(s.name for s in all_skills) or "none"
        return f"Skill '{skill_name}' not found. Available: {available}"

    params_dict: dict[str, str] = {}
    if params:
        try:
            params_dict = json.loads(params)
        except (json.JSONDecodeError, TypeError) as exc:
            return f"Invalid params JSON: {exc}"

    try:
        rendered = _default_injector.inject(skill, context, params_dict)
    except ValueError as exc:
        return f"Parameter error: {exc}"

    return f"[Skill: {skill.name}]\n\n{rendered}"


@tool
def run_skill_chain(steps: str, context: str = "") -> str:
    """Runs a sequence of skills as a chain. Steps is a comma-separated list of skill names.

    Args:
        steps: Comma-separated list of skill names to execute in order.
        context: Context string passed to each step.
    """
    if not steps or not steps.strip():
        return "Please provide at least one skill name."

    step_names = [s.strip() for s in steps.split(",") if s.strip()]
    if not step_names:
        return "Please provide at least one skill name."

    try:
        pipeline = ChainPipeline(_default_loader, _default_injector)
        result = pipeline.build(step_names, context)
    except ValueError as exc:
        return f"Chain error: {exc}"

    step_prompts = "\n\n---\n\n".join(result.steps)
    return f"{result.instructions}\n\n---\n\n{step_prompts}"


@tool
def skill_view(skill_name: str, file_path: str = "") -> str:
    """Views the prompt, instructions, and support files of a skill package.

    Args:
        skill_name: Name of the skill to view.
        file_path: Optional relative path to a support file (e.g. 'references/nmap_probes.md', 'templates/config.yaml', 'scripts/verify.py'). If omitted, views the main skill instructions.
    """
    skill = _default_loader.get_by_name(skill_name)
    if not skill:
        all_skills = _default_loader.load_all()
        available = ", ".join(s.name for s in all_skills) or "none"
        return f"Skill '{skill_name}' not found. Available: {available}"

    if not file_path or not file_path.strip():
        out = [
            f"# Skill: {skill.name} (v{skill.version})",
            f"**Category:** {skill.category}",
            f"**Description:** {skill.description}",
            f"**Triggers:** {', '.join(skill.triggers)}",
        ]
        if skill.is_package and skill.support_files:
            out.append("\n## Support Files:")
            for rel in sorted(skill.support_files):
                out.append(f"  • `{rel}`")
        out.append(f"\n## Instructions / Prompt:\n{skill.prompt}")
        return "\n".join(out)

    target_rel = file_path.strip().lstrip("/")
    if skill.support_files and target_rel in skill.support_files:
        full_path = Path(skill.support_files[target_rel])
        if full_path.is_file():
            return f"# File: {skill.name} / {target_rel}\n\n{full_path.read_text(encoding='utf-8')}"

    if skill.package_dir:
        candidate = Path(skill.package_dir) / target_rel
        if candidate.is_file():
            return f"# File: {skill.name} / {target_rel}\n\n{candidate.read_text(encoding='utf-8')}"

    avail_files = list(skill.support_files.keys()) if skill.support_files else ["None"]
    return f"Support file '{file_path}' not found in skill '{skill.name}'. Available: {', '.join(avail_files)}"


@tool
def skill_manage(
    action: str,
    skill_name: str,
    file_path: str = "",
    content: str = "",
    category: str = "general",
    description: str = "",
    triggers: str = "",
) -> str:
    """Manages skill packages by creating new skills or authoring support files.

    Args:
        action: Action to perform: 'create' (create new skill package), 'write_file' (write or update a support file in references/templates/scripts), 'list_files' (list files in a skill package).
        skill_name: Name of the skill package (e.g. 'custom_recon_workflow').
        file_path: Relative path for write_file (must start with references/, templates/, or scripts/).
        content: Text content to write into the file or SKILL.md.
        category: Category for new skill ('research', 'writing', 'productivity', 'data', 'communication', 'general').
        description: Description for new skill.
        triggers: Comma-separated triggers for new skill.
    """
    clean_name = re.sub(r"[^\w\-]", "_", skill_name.strip().lower())
    if not clean_name:
        return "Error: skill_name must be non-empty"

    if action == "list_files":
        skill = _default_loader.get_by_name(skill_name)
        if not skill:
            return f"Skill '{skill_name}' not found."
        if not skill.support_files:
            return f"Skill '{skill.name}' has no support files (is_package={skill.is_package})."
        return f"Support files for {skill.name}:\n" + "\n".join(
            f"  • {f}" for f in sorted(skill.support_files)
        )

    if action == "create":
        target_dir = SKILLS_DIR / clean_name
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "references").mkdir(exist_ok=True)
        (target_dir / "templates").mkdir(exist_ok=True)
        (target_dir / "scripts").mkdir(exist_ok=True)

        triggers_list = (
            [t.strip() for t in triggers.split(",") if t.strip()]
            if triggers
            else [clean_name]
        )
        skill_md = target_dir / "SKILL.md"

        frontmatter = [
            "---",
            f"name: {skill_name.strip()}",
            f"category: {category if category in ALLOWED_CATEGORIES else 'general'}",
            f"description: {description.strip() or 'Custom procedural skill'}",
            f"triggers: [{', '.join(triggers_list)}]",
            "version: '1.0'",
            "---",
            content.strip()
            or f"# {skill_name.strip()}\n\nProcedural instructions and guidelines.",
        ]
        skill_md.write_text("\n".join(frontmatter), encoding="utf-8")
        _default_loader.invalidate_cache()
        return f"Successfully created skill package '{skill_name}' at {target_dir}"

    if action == "write_file":
        if not file_path or not file_path.strip():
            return "Error: file_path is required for write_file (e.g. 'references/notes.md')"

        clean_rel = file_path.strip().lstrip("/")
        valid_prefixes = ("references/", "templates/", "scripts/", "assets/")
        if not any(clean_rel.startswith(p) for p in valid_prefixes):
            return (
                f"Error: file_path must start with one of: {', '.join(valid_prefixes)}"
            )

        skill = _default_loader.get_by_name(skill_name)
        if skill and skill.package_dir:
            pkg_path = Path(skill.package_dir)
        else:
            pkg_path = SKILLS_DIR / clean_name
            pkg_path.mkdir(parents=True, exist_ok=True)

        dest_file = pkg_path / clean_rel
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        dest_file.write_text(content, encoding="utf-8")
        _default_loader.invalidate_cache()
        return f"Successfully wrote {clean_rel} in skill '{skill_name}'"

    return f"Unknown action '{action}'. Valid actions: create, write_file, list_files."
