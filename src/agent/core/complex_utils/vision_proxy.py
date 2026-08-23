import base64
import copy
import hashlib
import logging
import time
from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage

from src.agent.core.complex_utils.vision_model_manager import get_vision_llm
from src.agent.core.complex_utils.vision_qwen3vl import parse_qwen3vl_response
from src.agent.core.complex_utils.vision_schema import (
    VISION_OCR_SYSTEM,
    VISION_OCR_USER,
    format_vision_for_cloud,
    parse_vision_payload,
)
from src.config.config_loader import config

logger = logging.getLogger(__name__)

_TRANSCRIPTION_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL = float(config.get("cloud.vision_transcription_cache_ttl", 3600))


def _image_cache_key(image_url: str) -> str:
    """Hash image URL or base64 prefix for transcription cache lookup."""
    sample = image_url[:8192] if len(image_url) > 8192 else image_url
    return hashlib.sha256(sample.encode("utf-8", errors="replace")).hexdigest()[:24]


def _bytes_cache_key(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes[:65536]).hexdigest()[:24]


def _get_cached_transcription(key: str) -> str | None:
    entry = _TRANSCRIPTION_CACHE.get(key)
    if not entry:
        return None
    ts, text = entry
    if time.monotonic() - ts > _CACHE_TTL:
        del _TRANSCRIPTION_CACHE[key]
        return None
    return text


def _store_transcription(key: str, text: str) -> None:
    _TRANSCRIPTION_CACHE[key] = (time.monotonic(), text)


def _vision_prompt_mode() -> str:
    return str(config.get("cloud.vision_prompt_mode", "qwen3vl")).lower()


def _raw_to_cloud_text(raw: str) -> str:
    mode = _vision_prompt_mode()
    payload = None
    if mode in ("qwen3vl", "standard"):
        payload = parse_qwen3vl_response(raw)
    if payload is None:
        payload = parse_vision_payload(raw)
    if payload is None:
        payload = {
            "text_blocks": [{"text": raw.strip(), "bbox": None}],
            "ui_elements": [],
            "subjects": ["unparsed"],
            "confidence": 0.5,
        }
    return format_vision_for_cloud(payload)


def _build_vlm_messages(image_url: str) -> list:
    """Build VLM messages for qwen3vl (default) mode."""
    # standard mode (default): natural-language system + user with image
    system_text = str(
        config.get(
            "cloud.vision_qwen3vl_system",
            VISION_OCR_SYSTEM,
        )
    )
    user_text = str(
        config.get(
            "cloud.vision_qwen3vl_user",
            VISION_OCR_USER,
        )
    )
    return [
        SystemMessage(content=system_text),
        HumanMessage(
            content=[
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]
        ),
    ]


async def _invoke_vision_vlm(image_url: str) -> str:
    vlm_messages = _build_vlm_messages(image_url)
    vlm_llm = await get_vision_llm()
    response = await vlm_llm.ainvoke(vlm_messages)
    raw = str(response.content).strip()
    if not raw:
        raise ValueError("empty transcription from local VLM")
    return _raw_to_cloud_text(raw)


async def transcribe_image_url(image_url: str) -> str:
    """Transcribe a data URL or remote image URL to cloud-ready text."""
    cache_key = _image_cache_key(image_url)
    cached = _get_cached_transcription(cache_key)
    if cached is not None:
        return cached
    text = await _invoke_vision_vlm(image_url)
    _store_transcription(cache_key, text)
    return text


async def transcribe_crop(
    image_bytes: bytes,
    *,
    mime_type: str = "image/png",
) -> str:
    """Transcribe a screen-assist crop (Phase 3 hook)."""
    cache_key = _bytes_cache_key(image_bytes)
    cached = _get_cached_transcription(cache_key)
    if cached is not None:
        return cached
    b64 = base64.b64encode(image_bytes).decode("ascii")
    image_url = f"data:{mime_type};base64,{b64}"
    text = await _invoke_vision_vlm(image_url)
    _store_transcription(cache_key, text)
    return text


async def process_vision_messages(
    messages: list,
    *,
    reanonymize: Callable[[str], tuple[str, dict]] | None = None,
) -> tuple[list, bool]:
    """
    Scan messages for ``image_url`` blocks and transcribe via local VLM.

    Returns processed messages and whether every image was transcribed successfully.
    """
    processed_messages = []
    proxy_ok = True

    for msg in messages:
        if not isinstance(msg, HumanMessage) or not isinstance(msg.content, list):
            processed_messages.append(msg)
            continue

        new_content = []
        has_image = False

        for block in msg.content:
            if isinstance(block, dict) and block.get("type") == "image_url":
                has_image = True
                image_url = block.get("image_url", {}).get("url", "")
                cache_key = _image_cache_key(image_url)
                transcription = _get_cached_transcription(cache_key)

                if transcription is None:
                    logger.info(
                        "[vision_proxy] Intercepted image. Sending to local VLM (%s).",
                        _vision_prompt_mode(),
                    )
                    try:
                        transcription = await transcribe_image_url(image_url)
                        logger.info(
                            "[vision_proxy] VLM transcription complete (%d chars).",
                            len(transcription),
                        )
                    except Exception as e:
                        proxy_ok = False
                        logger.error(
                            "[vision_proxy] Local VLM transcription failed: %s", e
                        )
                        new_content.append(block)
                        continue
                else:
                    logger.info(
                        "[vision_proxy] Using cached transcription (%d chars).",
                        len(transcription),
                    )

                if reanonymize:
                    transcription, _ = reanonymize(transcription)

                new_content.append(
                    {
                        "type": "text",
                        "text": f"\n\n{transcription}\n\n",
                    }
                )
            else:
                new_content.append(block)

        if has_image:
            new_msg = copy.copy(msg)
            new_msg.content = new_content
            processed_messages.append(new_msg)
        else:
            processed_messages.append(msg)

    return processed_messages, proxy_ok
