"""Unit tests for SkillLearnerEngine and hierarchical skill management tools."""

import tempfile
from pathlib import Path

from src.memory.skills_learner import SkillLearnerEngine
from src.tools.skills import (
    SkillLoader,
    _default_loader,
    skill_manage,
    skill_view,
)


def test_skill_learner_create_skill():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = SkillLearnerEngine(skills_dir=Path(tmpdir))
        payload = {
            "has_learning": True,
            "action": "create_skill",
            "target_skill": "nmap_custom_scan",
            "category": "research",
            "content": "# Nmap Custom Scan\n\nAlways use -sC -sV -Pn for filtered targets.",
            "rationale": "Learned from pentest subnet scan",
        }
        res = engine.apply_learning(payload)
        assert res["applied"] is True
        assert res["action"] == "create_skill"
        assert (Path(tmpdir) / "nmap_custom_scan" / "SKILL.md").is_file()


def test_skill_learner_add_support_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_path = Path(tmpdir)
        engine = SkillLearnerEngine(skills_dir=skills_path)
        payload = {
            "has_learning": True,
            "action": "add_support_file",
            "target_skill": "web_recon",
            "folder_type": "references",
            "relative_path": "references/cms_fingerprints.md",
            "content": "Wordpress wp-content endpoints...",
            "rationale": "CMS detection notes",
        }
        res = engine.apply_learning(payload)
        assert res["applied"] is True
        assert (
            skills_path / "web_recon" / "references" / "cms_fingerprints.md"
        ).is_file()


def test_skill_learner_patch_skill():
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_path = Path(tmpdir)
        pkg_dir = skills_path / "test_skill"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "SKILL.md").write_text(
            "---\nname: test_skill\ndescription: Test\ntriggers: [test]\ncategory: general\n---\n# Test Skill\n\nBase prompt.",
            encoding="utf-8",
        )

        engine = SkillLearnerEngine(skills_dir=skills_path)
        payload = {
            "has_learning": True,
            "action": "patch_active",
            "target_skill": "test_skill",
            "content": "Avoid using heavy threads on weak routers.",
            "rationale": "Connection timeout correction",
        }
        res = engine.apply_learning(payload)
        assert res["applied"] is True
        content = (pkg_dir / "SKILL.md").read_text(encoding="utf-8")
        assert "Learned Pitfalls & Workarounds" in content
        assert "Avoid using heavy threads" in content


def test_skill_manage_and_view_tools():
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = SkillLoader(Path(tmpdir))
        create_res = skill_manage.invoke(
            {
                "action": "create",
                "skill_name": "auto_tool_test",
                "category": "writing",
                "description": "Auto tool test skill",
                "triggers": "auto_tool, test_tool",
                "content": "# Auto Tool\n\nInstructions here.",
            }
        )
        assert "Successfully created" in create_res

        write_res = skill_manage.invoke(
            {
                "action": "write_file",
                "skill_name": "auto_tool_test",
                "file_path": "references/guide.md",
                "content": "Reference guide content.",
            }
        )
        assert "Successfully wrote" in write_res

        view_main = skill_view.invoke({"skill_name": "auto_tool_test"})
        assert "Auto Tool" in view_main

        view_ref = skill_view.invoke(
            {
                "skill_name": "auto_tool_test",
                "file_path": "references/guide.md",
            }
        )
        assert "Reference guide content" in view_ref
