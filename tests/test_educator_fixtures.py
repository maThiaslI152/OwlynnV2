"""UID10667 educator eval fixture validation."""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "assets" / "eval_fixtures" / "uid10667"


def test_chapter1_pdf_exists():
    assert (FIXTURE_DIR / "chapter1-digital-literacy.pdf").is_file()


def test_keywords_json_structure():
    data = json.loads((FIXTURE_DIR / "keywords.json").read_text(encoding="utf-8"))
    assert data.get("course")
    chapters = data.get("chapters") or {}
    ch1 = chapters.get("chapter1-digital-literacy.pdf") or []
    assert len(ch1) >= 2
    assert any("digital" in k.lower() for k in ch1)


def test_criticism_keyword_present():
    data = json.loads((FIXTURE_DIR / "keywords.json").read_text(encoding="utf-8"))
    assert data.get("criticism_prompt_keyword")
