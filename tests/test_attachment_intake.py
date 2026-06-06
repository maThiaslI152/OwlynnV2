import base64

import pytest

from src.api.attachment_intake import (
    is_vision_filename,
    is_vision_mime,
    normalize_file_attachment,
)
from src.api.shared import build_message_content


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PNG_B64 = base64.b64encode(PNG_BYTES).decode("ascii")


@pytest.mark.parametrize(
    "filename",
    ["photo.png", "photo.jpg", "photo.jpeg", "pic.webp", "anim.gif"],
)
def test_is_vision_filename(filename):
    assert is_vision_filename(filename) is True


def test_is_vision_filename_rejects_text():
    assert is_vision_filename("notes.txt") is False


def test_normalize_data_url_without_explicit_type():
    data_url = f"data:image/png;base64,{PNG_B64}"
    normalized = normalize_file_attachment({"name": "shot.png", "data": data_url})
    assert normalized is not None
    assert normalized["type"] == "image/png"
    assert normalized["data"] == PNG_B64
    assert normalized["raw_bytes"] == PNG_BYTES


def test_normalize_infers_mime_from_extension():
    normalized = normalize_file_attachment({"name": "shot.png", "data": PNG_B64})
    assert normalized is not None
    assert normalized["type"] == "image/png"


def test_is_vision_mime():
    assert is_vision_mime("image/png") is True
    assert is_vision_mime("text/plain") is False


@pytest.mark.asyncio
async def test_build_message_content_image_from_data_url():
    data_url = f"data:image/png;base64,{PNG_B64}"
    content = await build_message_content(
        "describe this",
        [{"name": "shot.png", "data": data_url}],
    )
    assert isinstance(content, list)
    image_blocks = [b for b in content if b.get("type") == "image_url"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_build_message_content_image_with_explicit_type():
    content = await build_message_content(
        "describe this",
        [{"name": "shot.png", "type": "image/png", "data": PNG_B64}],
    )
    assert isinstance(content, list)
    assert any(b.get("type") == "image_url" for b in content)
