"""Tests for DeepSeek cloud payload assembly and security."""

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

sys.modules["mem0"] = MagicMock()


@pytest.fixture
def mock_profile():
    return {
        "name": "Test User",
        "cloud_brief_enabled": True,
        "cloud_anonymization_enabled": True,
        "cloud_brief_max_chars": 8000,
        "custom_sensitive_terms": [],
    }


class TestCloudBriefGate:
    @pytest.mark.asyncio
    async def test_tool_loop_skips_brief(self, mock_profile):
        from src.agent.cloud.cloud_payload import prepare_cloud_payload

        async def noop_vision(messages):
            return messages, True

        messages = [
            HumanMessage(content="hello"),
            AIMessage(
                content="",
                tool_calls=[{"id": "1", "name": "read_workspace_file", "args": {}}],
            ),
            ToolMessage(content="file contents", tool_call_id="1"),
        ]
        with patch(
            "src.agent.cloud.cloud_payload.get_profile",
            return_value=mock_profile,
        ):
            payload = await prepare_cloud_payload(
                state={"messages": messages},
                system_stable="stable core",
                volatile_suffix="volatile",
                trimmed_messages=messages,
                vision_processor=noop_vision,
            )
        assert len(payload.messages) == 3
        assert payload.cloud_brief_tokens_est == 0

    @pytest.mark.asyncio
    async def test_first_turn_uses_brief(self, mock_profile):
        from src.agent.cloud.cloud_payload import prepare_cloud_payload

        async def noop_vision(messages):
            return messages, True

        messages = [HumanMessage(content="Summarize project")]
        with (
            patch(
                "src.agent.cloud.cloud_payload.get_profile",
                return_value=mock_profile,
            ),
            patch(
                "src.agent.cloud.cloud_payload.build_cloud_brief",
                return_value="--- brief ---",
            ),
        ):
            payload = await prepare_cloud_payload(
                state={"messages": messages, "clarified_scope": {"goal": "test"}},
                system_stable="stable core",
                volatile_suffix="volatile",
                trimmed_messages=messages,
                vision_processor=noop_vision,
            )
        assert len(payload.messages) == 1
        assert payload.cloud_brief_tokens_est > 0


class TestCompactToolCallArgs:
    def test_completed_write_compacts_content(self):
        from src.agent.cloud.cloud_payload import (
            compact_tool_call_args_for_api,
            message_to_deepseek_dict,
            messages_to_deepseek_api,
        )

        huge = "x" * 5000
        args = compact_tool_call_args_for_api(
            "write_workspace_file",
            {"filename": "dashboard.css", "content": huge},
            completed=True,
        )
        assert args["content"].startswith("[written to dashboard.css")
        assert huge not in args["content"]

        messages = [
            HumanMessage(content="write file"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "tc1",
                        "name": "write_workspace_file",
                        "args": {"filename": "dashboard.css", "content": huge},
                    }
                ],
            ),
            ToolMessage(content="✅ Written", tool_call_id="tc1"),
        ]
        api_msgs = messages_to_deepseek_api(messages)
        tc_args = json.loads(api_msgs[1]["tool_calls"][0]["function"]["arguments"])
        assert huge not in tc_args["content"]
        assert "dashboard.css" in tc_args["content"]

    def test_pending_write_keeps_content(self):
        from src.agent.cloud.cloud_payload import (
            message_to_deepseek_dict,
        )

        huge = "y" * 1000
        msg = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "tc2",
                    "name": "write_workspace_file",
                    "args": {"filename": "a.txt", "content": huge},
                }
            ],
        )
        out = message_to_deepseek_dict(msg, completed_tool_call_ids=set())
        tc_args = json.loads(out["tool_calls"][0]["function"]["arguments"])
        assert huge in tc_args["content"]


class TestReasoningContentReplay:
    def test_message_converter_preserves_reasoning(self):
        from src.agent.cloud.cloud_payload import message_to_deepseek_dict

        msg = AIMessage(
            content="answer",
            additional_kwargs={"reasoning_content": "step by step"},
            tool_calls=[{"id": "tc1", "name": "web_search", "args": {"q": "x"}}],
        )
        out = message_to_deepseek_dict(msg)
        assert out["reasoning_content"] == "step by step"
        assert out["tool_calls"]


class TestStablePrefix:
    def test_stable_prompt_excludes_date(self):
        from src.agent.cloud.cloud_payload import COMPLEX_PROMPT_STABLE

        assert "{current_date}" not in COMPLEX_PROMPT_STABLE
        assert "{memory_context}" not in COMPLEX_PROMPT_STABLE


class TestLegacyRoutesAbsent:
    def test_graph_valid_complex_routes(self):
        import inspect
        import importlib.util

        spec = importlib.util.find_spec("src.agent.core.graph")
        assert spec is not None
        path = spec.origin
        assert path
        source = open(path, encoding="utf-8").read()
        assert "complex-vision" not in source
        assert "complex-longctx" not in source


class TestCloudBriefMemoryFilter:
    def test_filters_paths_and_emails(self):
        from src.agent.hitl.cloud_brief import _filter_memory_context

        raw = "Contact tim@example.com at /Users/tim/secret.txt api_key=sk-abc12345"
        cleaned = _filter_memory_context(raw)
        assert "tim@example.com" not in cleaned
        assert "/Users/tim" not in cleaned
        assert "sk-abc" not in cleaned


class TestVisionTranscriptionCache:
    @pytest.mark.asyncio
    async def test_cache_hit_avoids_second_vlm_call(self):
        from src.agent.core.complex_utils import vision_proxy as vp

        vp._TRANSCRIPTION_CACHE.clear()
        image_block = {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,AAAA"},
        }
        messages = [HumanMessage(content=[image_block])]

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = MagicMock(
            content='{"text_blocks":[{"text":"screenshot text"}],"subjects":[],"confidence":0.9}'
        )

        with patch(
            "src.agent.core.complex_utils.vision_proxy.get_vision_llm",
            AsyncMock(return_value=mock_llm),
        ):
            out1, ok1 = await vp.process_vision_messages(messages)
            out2, ok2 = await vp.process_vision_messages(messages)

        assert ok1 and ok2
        assert mock_llm.ainvoke.await_count == 1
        assert "screenshot text" in str(out2[0].content)


class TestAnonymizeToolCalls:
    def test_notebook_run_code_with_backslashes_does_not_crash(self):
        from src.agent.cloud.cloud_payload import _anonymize_tool_calls

        code = (
            "import matplotlib.pyplot as plt\n"
            "plt.rcParams['font.sans-serif'] = ['DejaVu Sans']\n"
            "path = r'\\Users\\tim\\data\\report.csv'\n"
            "label = '\\u041a\\u0438\\u0457\\u0432'\n"
            "plt.savefig('/tmp/chart.png')\n"
        )
        tool_calls = [
            {
                "id": "nb1",
                "name": "notebook_run",
                "args": {"code": code, "timeout": 60},
            }
        ]
        out, mapping = _anonymize_tool_calls(tool_calls, {}, None)
        assert "import matplotlib.pyplot as plt" in out[0]["args"]["code"]
        assert out[0]["args"]["timeout"] == 60
        assert isinstance(out[0]["args"]["code"], str)

    def test_anonymizes_email_in_tool_args_without_json_roundtrip(self):
        from src.agent.cloud.cloud_payload import _anonymize_tool_calls

        tool_calls = [
            {
                "id": "1",
                "name": "send_email",
                "args": {"to": "user@example.com", "body": "hello"},
            }
        ]
        out, mapping = _anonymize_tool_calls(tool_calls, {}, None)
        assert "user@example.com" not in out[0]["args"]["to"]
        assert mapping
        assert "user@example.com" in mapping.values()


class TestFallbackAnonymization:
    def test_deanonymize_restores_placeholders(self):
        from src.agent.core.complex import _deanonymize_ai_message

        mapping = {"[EMAIL_a4f2b9c1]": "real@example.com"}
        msg = AIMessage(content="Write to [EMAIL_a4f2b9c1]")
        restored = _deanonymize_ai_message(msg, mapping)
        assert "real@example.com" in restored.content


class TestFinalizeCloudVisibleContent:
    def test_uses_content_when_present(self):
        from src.agent.cloud.cloud_payload import (
            finalize_cloud_visible_content,
        )

        out = finalize_cloud_visible_content("Hello REST", "long reasoning chain")
        assert out == "Hello REST"

    def test_falls_back_to_reasoning_when_content_empty(self):
        from src.agent.cloud.cloud_payload import (
            finalize_cloud_visible_content,
        )

        out = finalize_cloud_visible_content("", "GraphQL comparison details")
        assert out == "GraphQL comparison details"
