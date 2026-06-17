"""Tests for .env / .env.local loading at startup."""

from __future__ import annotations

import os

from src.config.env_files import load_project_env_files


def test_load_project_env_files_applies_local_override(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=from-env\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text(
        "DEEPSEEK_API_KEY=from-local\n", encoding="utf-8"
    )
    load_project_env_files(tmp_path)
    assert os.environ["DEEPSEEK_API_KEY"] == "from-local"


def test_load_project_env_files_skips_missing_files(tmp_path, monkeypatch):
    monkeypatch.delenv("OWLYNN_TEST_DOTENV", raising=False)
    load_project_env_files(tmp_path)
    assert "OWLYNN_TEST_DOTENV" not in os.environ
