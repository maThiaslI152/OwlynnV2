import logging
import copy
from typing import Any
from langchain_core.messages import HumanMessage

from src.agent.llm import get_medium_llm

logger = logging.getLogger(__name__)


async def process_vision_messages(messages: list) -> list:
    """
    Scans messages for `image_url` blocks. If found, sends the image to the
    local vision model (medium-vision) to transcribe the image to text,
    then replaces the `image_url` block with a `text` block containing the transcription.

    This acts as a Vision-to-Text proxy for models like DeepSeek V4 that
    do not natively support multimodal inputs.
    """
    processed_messages = []

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

                logger.info(
                    "[vision_proxy] Intercepted image. Sending to local VLM for transcription."
                )

                try:
                    # Construct a temporary prompt just for the local vision model
                    vlm_messages = [
                        HumanMessage(
                            content=[
                                {
                                    "type": "text",
                                    "text": "Please describe this image in extreme detail, transcribing any text, code, or UI elements exactly as they appear. You are acting as the eyes for a blind, text-only AI model.",
                                },
                                {"type": "image_url", "image_url": {"url": image_url}},
                            ]
                        )
                    ]

                    vlm_llm = await get_medium_llm("vision")
                    response = await vlm_llm.ainvoke(vlm_messages)

                    transcription = str(response.content)
                    logger.info(
                        "[vision_proxy] VLM transcription complete (%d chars).",
                        len(transcription),
                    )

                    new_content.append(
                        {
                            "type": "text",
                            "text": f"\n\n[System Note: The user attached an image here. A local Vision Model transcribed it as follows:\n{transcription}\n]\n\n",
                        }
                    )
                except Exception as e:
                    logger.error("[vision_proxy] Local VLM transcription failed: %s", e)
                    new_content.append(
                        {
                            "type": "text",
                            "text": "\n\n[System Note: The user attached an image, but the local Vision-to-Text proxy failed to transcribe it.]\n\n",
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

    return processed_messages
