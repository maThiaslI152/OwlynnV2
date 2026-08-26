"""pgvector memory configuration assertions (source-level)."""

from pathlib import Path


def test_long_term_source_uses_configured_embedder():
    root = Path(__file__).resolve().parents[1]
    text = (root / "src/memory/long_term.py").read_text(encoding="utf-8")
    assert "get_embedding_model_name" in text or "text-embedding" in text
    assert "memory_vectors" in text
    # Legacy collection names should not be the active default
    assert '"cowork_memory"' not in text
    assert '"cowork_memory_mE5"' not in text


def test_embedding_dims_come_from_models_config():
    """Embedding dimensions resolve from models.embedding, not legacy qdrant keys."""
    from src.config.config_loader import ConfigLoader

    dims = ConfigLoader.get_embedding_dimensions()
    assert isinstance(dims, int)
    assert dims == 1024
