"""Regression: system folding must preserve multimodal image_url blocks."""

from langchain_core.messages import HumanMessage, SystemMessage

from src.agent.lm_studio_compat import fold_system_into_first_user


def test_fold_system_preserves_image_url_blocks():
    system = SystemMessage(content="You are a helpful assistant.")
    user = HumanMessage(
        content=[
            {"type": "text", "text": "What is in this image?"},
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,abc"},
            },
        ]
    )

    folded = fold_system_into_first_user(system, [user])

    assert len(folded) == 1
    assert isinstance(folded[0], HumanMessage)
    content = folded[0].content
    assert isinstance(content, list)
    image_blocks = [b for b in content if b.get("type") == "image_url"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["image_url"]["url"] == "data:image/png;base64,abc"
