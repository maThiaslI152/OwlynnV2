"""Phase 1 memory orchestration: PII, extraction schema, scenarios, compression."""

import json

from src.agent.pii_scrubber import scrub_for_storage
from src.memory.compression import compress_memory_for_cloud
from src.memory.extraction.schema import parse_extraction_response, validate_atom
from src.memory.scenarios import detect_scenario_id, format_scenario_context


def test_scrub_for_storage_redacts_email():
    text = "Contact me at alice@example.com for details."
    scrubbed, count = scrub_for_storage(text)
    assert "alice@example.com" not in scrubbed
    assert count >= 1


def test_parse_extraction_response_atoms():
    raw = json.dumps(
        {
            "atoms": [
                {
                    "tier": "L1",
                    "format": "jsdoc",
                    "content": "/** @fact scope Production web app only */",
                    "tags": ["pentest"],
                    "confidence": 0.9,
                }
            ]
        }
    )
    atoms = parse_extraction_response(raw)
    assert len(atoms) == 1
    assert atoms[0]["format"] == "jsdoc"


def test_validate_atom_rejects_short_content():
    assert validate_atom({"content": "short"}) is None


def test_detect_scenario_pentest():
    assert (
        detect_scenario_id("Run nmap enumeration against the staging target")
        == "pentest"
    )


def test_detect_scenario_research():
    assert (
        detect_scenario_id("Summarize research papers on transformer architectures")
        == "research"
    )


def test_format_scenario_context_includes_playbook():
    ctx = format_scenario_context("pentest")
    assert "Pentest playbook" in ctx
    assert "constraints" in ctx.lower()


def test_compress_memory_for_cloud_strips_filler():
    block = compress_memory_for_cloud(
        "- User prefers ap-southeast-1\n- None",
        knowledge_context="- Cached fact about REST APIs",
        max_chars=500,
    )
    assert "ap-southeast-1" in block
    assert "compressed" in block.lower()
