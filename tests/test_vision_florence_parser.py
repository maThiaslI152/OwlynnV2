"""Unit tests for Florence-2 vision response parsing."""

from src.agent.nodes.complex_utils.vision_florence import parse_florence_response
from src.agent.nodes.complex_utils.vision_schema import format_vision_for_cloud


def test_parse_plain_ocr_text():
    payload = parse_florence_response("ERROR: connection refused on :5432")
    assert payload is not None
    cloud = format_vision_for_cloud(payload)
    assert "connection refused" in cloud


def test_parse_ocr_dict_string():
    raw = "{' <OCR>': 'Hello world'}"
    payload = parse_florence_response(raw.replace(" <OCR>", "<OCR>"))
    assert payload is not None
    assert any("Hello" in b["text"] for b in payload["text_blocks"])


def test_parse_ocr_with_region_labels():
    raw = str(
        {
            "<OCR_WITH_REGION>": {
                "labels": ["Submit", "Cancel"],
                "quad_boxes": [[0, 0, 1, 1, 2, 2, 3, 3], [4, 4, 5, 5, 6, 6, 7, 7]],
            }
        }
    )
    payload = parse_florence_response(raw)
    assert payload is not None
    assert len(payload["text_blocks"]) >= 2
