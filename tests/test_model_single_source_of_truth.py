"""
Contract & Integrity tests verifying defaults.yaml and ConfigLoader as the
Single Source of Truth (SSOT) for all model names, dimensions, and configurations.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from src.config.config_loader import ConfigLoader, config, get_model_config


def test_defaults_yaml_contains_all_core_model_slots():
    """Verify defaults.yaml defines all required model slots and properties."""
    ConfigLoader.reload()
    raw_cfg = ConfigLoader.get_config()
    models = raw_cfg.get("models", {})

    assert "main" in models, "models.main must be present in defaults.yaml"
    assert "vision" in models, "models.vision must be present in defaults.yaml"
    assert "embedding" in models, "models.embedding must be present in defaults.yaml"
    assert "pentest" in models, "models.pentest must be present in defaults.yaml"
    assert "cloud" in models, "models.cloud must be present in defaults.yaml"

    # Verify main model properties
    main_cfg = models["main"]
    assert "model_name" in main_cfg
    assert "base_url" in main_cfg
    assert "context_window" in main_cfg

    # Verify embedding properties
    embed_cfg = models["embedding"]
    assert "model_name" in embed_cfg
    assert "dims" in embed_cfg
    assert int(embed_cfg["dims"]) == 1024


def test_config_loader_getters_return_expected_defaults():
    """Verify ConfigLoader getter methods return the canonical defaults."""
    ConfigLoader.reload()

    assert (
        config.get_main_model_name()
        == "gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m"
    )
    assert (
        config.get_small_model_name()
        == "gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m"
    )
    assert (
        config.get_complex_local_model_name()
        == "gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m"
    )
    assert config.get_vision_model_name() == "baidu.unlimited-ocr"
    assert config.get_embedding_model_name() == "text-embedding-mxbai-embed-large-v1"
    assert config.get_embedding_dimensions() == 1024
    assert (
        config.get_pentest_model_name()
        == "gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m"
    )
    assert config.get_cloud_model_name() == "deepseek-v4-flash"
    assert config.get_models_provider() == "lm_studio"
    assert config.get_cloud_provider() == "deepseek"
    assert config.get_main_model_context_window() == 16384


def test_env_var_overrides_dynamically_update_all_model_getters():
    """Verify environment variables override defaults without modifying code."""
    env_overrides = {
        "MAIN_LLM_MODEL_NAME": "custom/main-model-70b",
        "MAIN_LLM_BASE_URL": "http://10.0.0.1:8080/v1",
        "VISION_LLM_MODEL_NAME": "custom/vision-ocr-v2",
        "VISION_LLM_BASE_URL": "http://10.0.0.1:8081/v1",
        "EMBEDDING_LLM_MODEL_NAME": "custom/embed-model-v3",
        "EMBEDDING_LLM_BASE_URL": "http://10.0.0.1:8082/v1",
        "EMBEDDING_DIMS": "1536",
        "PENTEST_LLM_MODEL_NAME": "custom/pentest-expert-14b",
        "PENTEST_LLM_BASE_URL": "http://10.0.0.1:8083/v1",
        "CLOUD_LLM_MODEL_NAME": "custom/cloud-frontier-v1",
        "CLOUD_LLM_BASE_URL": "https://api.custom-cloud.ai/v1",
        "MODELS_PROVIDER": "ollama",
    }

    with patch.dict(os.environ, env_overrides, clear=False):
        ConfigLoader.reload()

        assert config.get_main_model_name() == "custom/main-model-70b"
        assert config.get_main_model_base_url() == "http://10.0.0.1:8080/v1"
        assert config.get_vision_model_name() == "custom/vision-ocr-v2"
        assert config.get_vision_model_base_url() == "http://10.0.0.1:8081/v1"
        assert config.get_embedding_model_name() == "custom/embed-model-v3"
        assert config.get_embedding_base_url() == "http://10.0.0.1:8082/v1"
        assert config.get_embedding_dimensions() == 1536
        assert config.get_pentest_model_name() == "custom/pentest-expert-14b"
        assert config.get_pentest_model_base_url() == "http://10.0.0.1:8083/v1"
        assert config.get_cloud_model_name() == "custom/cloud-frontier-v1"
        assert config.get_cloud_base_url() == "https://api.custom-cloud.ai/v1"
        assert config.get_models_provider() == "ollama"

    # Reset
    ConfigLoader.reload()


def test_get_model_config_matches_main_and_small():
    """Verify get_model_config('main') and get_model_config('small') return matching configs."""
    ConfigLoader.reload()
    main_cfg = get_model_config("main")
    small_cfg = get_model_config("small")

    assert main_cfg["model_name"] == config.get_main_model_name()
    assert small_cfg["model_name"] == config.get_main_model_name()
    assert main_cfg["context_window"] == small_cfg["context_window"]
