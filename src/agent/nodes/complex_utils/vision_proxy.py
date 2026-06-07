import hashlib
import logging
import time
import copy
from typing import Callable, Optional

from langchain_core.messages import HumanMessage

from src.agent.llm import get_medium_llm
from src.config.config_loader import config

logger = logging.getLogger(__name__)

_TRANSCRIPTION_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL = float(config.get("cloud.vision_transcription_cache_ttl", 3600))


def _image_cache_key(image_url: str) -> str:
    """Hash image URL or base64 prefix for transcription cache lookup."""
    sample = image_url[:8192] if len(image_url) > 8192 else image_url
    return hashlib.sha256(sample.encode("utf-8", errors="replace")).hexdigest()[:24]


def _get_cached_transcription(key: str) -> Optional[str]:
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


async def process_vision_messages(
    messages: list,
    *,
    reanonymize: Optional[Callable[[str], tuple[str, dict]]] = None,
) -> tuple[list, bool]:
    """
    Scan messages for ``image_url`` blocks and transcribe via local VLM.

    Parameters
    ----------
    reanonymize
        Optional ``(text) -> (text, mapping)`` hook applied to each transcription
        before it is merged into the cloud prompt.

    Returns
    -------
    tuple[list, bool]
        Processed messages and whether every image was transcribed successfully.
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
                        "[vision_proxy] Intercepted image. Sending to local VLM for transcription."
                    )
                    try:
                        vlm_messages = [
                            HumanMessage(
                                content=[
                                    {
                                        "type": "text",
                                        "text": "Please describe this image in extreme detail, transcribing any text, code, or UI elements exactly as they appear. You are acting as the eyes for a blind, text-only AI model.",
                                    },
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": image_url},
                                    },
                                ]
                            )
                        ]

                        vlm_llm = await get_medium_llm("vision")
                        response = await vlm_llm.ainvoke(vlm_messages)

                        transcription = str(response.content).strip()
                        if not transcription:
                            raise ValueError("empty transcription from local VLM")

                        _store_transcription(cache_key, transcription)
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
                        "text": f"\n\n[System Note: The user attached an image here. A local Vision Model transcribed it as follows:\n{transcription}\n]\n\n",
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
