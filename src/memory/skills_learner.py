"""
SkillLearnerEngine — Autonomous procedural skill synthesis and refinement.

Inspired by Hermes Agent's closed learning loop, this module takes procedural
insights extracted by the background worker and applies the 4-tier skill cascade:
  1. Patch active skill (append pitfalls or update instructions)
  2. Update domain umbrella skill
  3. Author support files (references/, templates/, scripts/)
  4. Synthesize a new class-level skill package
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from src.config.audit_log import audit_info
from src.tools.skills import (
    ALLOWED_CATEGORIES,
    SKILLS_DIR,
    _default_loader,
)

logger = logging.getLogger(__name__)


class SkillLearnerEngine:
    """Applies learned procedural rules, workarounds, and scripts to the skills repository."""

    def __init__(self, skills_dir: Path | None = None) -> None:
        self.skills_dir = skills_dir or SKILLS_DIR
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def apply_learning(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Apply a structured procedural skill update payload."""
        if not payload or not payload.get("has_learning"):
            return {"applied": False, "reason": "No procedural learning detected"}

        action = payload.get("action", "none")
        target_skill = payload.get("target_skill", "").strip()
        folder_type = payload.get("folder_type", "references").strip()
        rel_path = payload.get("relative_path", "").strip().lstrip("/")
        content = payload.get("content", "").strip()
        rationale = payload.get("rationale", "").strip()
        category = payload.get("category", "general").strip()

        if not content:
            return {"applied": False, "reason": "Empty content in learning payload"}

        clean_skill_name = (
            re.sub(r"[^\w\-]", "_", target_skill.lower())
            if target_skill
            else "general_workflow"
        )

        if action in ("patch_active", "update_umbrella"):
            return self._patch_skill(clean_skill_name, content, rationale)

        elif action == "add_support_file":
            if not rel_path:
                rel_path = f"{folder_type}/{clean_skill_name}_notes.md"
            return self._write_support_file(
                clean_skill_name, rel_path, content, rationale
            )

        elif action == "create_skill":
            return self._create_class_level_skill(
                clean_skill_name, content, category, rationale
            )

        return {"applied": False, "reason": f"Unhandled action '{action}'"}

    def _patch_skill(
        self, skill_name: str, patch_content: str, rationale: str
    ) -> dict[str, Any]:
        """Append or patch an existing skill's instructions/pitfalls."""
        if (self.skills_dir / skill_name / "SKILL.md").is_file():
            target_file = self.skills_dir / skill_name / "SKILL.md"
        elif (self.skills_dir / f"{skill_name}.md").is_file():
            target_file = self.skills_dir / f"{skill_name}.md"
        else:
            skill = _default_loader.get_by_name(skill_name)
            if skill and skill.package_dir:
                target_file = Path(skill.package_dir) / "SKILL.md"
            elif skill and (self.skills_dir / skill.file).is_file():
                target_file = self.skills_dir / skill.file
            else:
                # Skill doesn't exist yet, redirect to support file or creation
                return self._write_support_file(
                    skill_name,
                    f"references/{skill_name}_lessons.md",
                    patch_content,
                    rationale,
                )

        try:
            current_text = target_file.read_text(encoding="utf-8")
            if "## Learned Pitfalls & Workarounds" not in current_text:
                updated_text = (
                    current_text
                    + "\n\n## Learned Pitfalls & Workarounds\n"
                    + f"- {patch_content.strip()}"
                )
            else:
                updated_text = current_text + f"\n- {patch_content.strip()}"

            target_file.write_text(updated_text, encoding="utf-8")
            _default_loader.invalidate_cache()
            audit_info(
                "skill.learned",
                "patch",
                skill=skill_name,
                file=str(target_file),
                rationale=rationale,
            )
            return {
                "applied": True,
                "action": "patch",
                "skill": skill_name,
                "file": str(target_file),
                "rationale": rationale,
            }
        except Exception as exc:
            logger.warning("Failed to patch skill %s: %s", skill_name, exc)
            return {"applied": False, "error": str(exc)}

    def _write_support_file(
        self, skill_name: str, rel_path: str, content: str, rationale: str
    ) -> dict[str, Any]:
        """Write a reference document, template, or script for a skill."""
        if (self.skills_dir / skill_name).is_dir():
            pkg_path = self.skills_dir / skill_name
        else:
            skill = _default_loader.get_by_name(skill_name)
            if skill and skill.package_dir:
                pkg_path = Path(skill.package_dir)
            else:
                pkg_path = self.skills_dir / skill_name
                pkg_path.mkdir(parents=True, exist_ok=True)
                # Create root SKILL.md if not present
                skill_md = pkg_path / "SKILL.md"
                if not skill_md.is_file():
                    frontmatter = (
                        f"---\nname: {skill_name}\ndescription: Auto-created skill package\n"
                        f"triggers: [{skill_name}]\ncategory: general\n---\n"
                        f"# {skill_name}\n\nProcedural workflows and support files."
                    )
                    skill_md.write_text(frontmatter, encoding="utf-8")

        dest_file = pkg_path / rel_path
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        dest_file.write_text(content, encoding="utf-8")
        _default_loader.invalidate_cache()

        audit_info(
            "skill.learned",
            "support_file",
            skill=skill_name,
            file=str(dest_file),
            rationale=rationale,
        )
        return {
            "applied": True,
            "action": "add_support_file",
            "skill": skill_name,
            "file": str(dest_file),
            "rationale": rationale,
        }

    def _create_class_level_skill(
        self, skill_name: str, content: str, category: str, rationale: str
    ) -> dict[str, Any]:
        """Synthesize a new class-level skill package."""
        target_dir = self.skills_dir / skill_name
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "references").mkdir(exist_ok=True)
        (target_dir / "templates").mkdir(exist_ok=True)
        (target_dir / "scripts").mkdir(exist_ok=True)

        cat = category if category in ALLOWED_CATEGORIES else "general"
        skill_md = target_dir / "SKILL.md"
        frontmatter = [
            "---",
            f"name: {skill_name}",
            f"category: {cat}",
            "description: Procedural skill synthesized from user workflow",
            f"triggers: [{skill_name}]",
            "version: '1.0'",
            "---",
            content.strip(),
        ]
        skill_md.write_text("\n".join(frontmatter), encoding="utf-8")
        _default_loader.invalidate_cache()

        audit_info(
            "skill.learned",
            "create",
            skill=skill_name,
            file=str(skill_md),
            rationale=rationale,
        )
        return {
            "applied": True,
            "action": "create_skill",
            "skill": skill_name,
            "file": str(skill_md),
            "rationale": rationale,
        }


_default_skill_learner = SkillLearnerEngine()
