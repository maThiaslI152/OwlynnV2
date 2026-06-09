"""Vision proxy JSON schema parse + cloud formatting."""

from src.agent.nodes.complex_utils.vision_schema import (
    format_vision_for_cloud,
    normalize_vision_payload,
    parse_vision_payload,
)


def test_parse_vision_payload_valid_json():
    raw = """{
      "text_blocks": [{"text": "hello world", "bbox": null}],
      "ui_elements": [{"role": "button", "label": "OK"}],
      "subjects": ["form"],
      "confidence": 0.95
    }"""
    payload = parse_vision_payload(raw)
    assert payload is not None
    assert payload["text_blocks"][0]["text"] == "hello world"
    assert payload["ui_elements"][0]["label"] == "OK"


def test_parse_vision_payload_strips_fences():
    raw = '```json\n{"text_blocks":[{"text":"x"}],"subjects":[],"confidence":0.8}\n```'
    payload = parse_vision_payload(raw)
    assert payload is not None
    assert payload["text_blocks"][0]["text"] == "x"


def test_parse_vision_payload_invalid_returns_none():
    assert parse_vision_payload("not json") is None


def test_format_vision_for_cloud_dense_block():
    payload = normalize_vision_payload(
        {
            "text_blocks": [{"text": "error: connection refused"}],
            "ui_elements": [],
            "subjects": ["terminal"],
            "confidence": 0.88,
        }
    )
    text = format_vision_for_cloud(payload)
    assert "[Vision sensor output" in text
    assert "TEXT: error: connection refused" in text
    assert "terminal" in text
