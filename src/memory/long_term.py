"""
Long-Term Memory Management using Mem0 and Qdrant.

This module initializes the Mem0 memory manager with a local Qdrant instance.
Embeddings are served by LM Studio (nomic-embed-text-v1.5) to avoid loading
a separate HuggingFace model in the Python process.
"""

import os
import logging

logger = logging.getLogger(__name__)

from src.config.audit_log import audit_info, audit_warn
from src.config.config_loader import config

from mem0 import Memory  # noqa: E402

_qdrant_host = config.get("external_services.qdrant.host", "localhost")
_qdrant_port = int(config.get("external_services.qdrant.port", 6333))
_qdrant_collection = config.get(
    "external_services.qdrant.collection_name", "cowork_memory_nomic"
)
_qdrant_dims = int(config.get("external_services.qdrant.embedding_dims", 768))
_embed_model = config.get(
    "models.embedding.model_name", "text-embedding-nomic-embed-text-v1.5-embedding"
)
_embed_url = config.get("models.embedding.base_url", "http://127.0.0.1:1234/v1")

mem0_config = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "host": _qdrant_host,
            "port": _qdrant_port,
            "collection_name": _qdrant_collection,
            "embedding_model_dims": _qdrant_dims,
        },
    },
    "embedder": {
        "provider": "lmstudio",
        "config": {
            "model": _embed_model,
            "embedding_dims": _qdrant_dims,
            "lmstudio_base_url": _embed_url,
        },
    },
}

try:
    # Mem0 implicitly initializes its internal default OpenAI client during setup,
    # so we provide a dummy key only during initialization to prevent api_key errors,
    # but we disable its automatic LLM calls below using infer=False.
    # We use setdefault so any user-provided key takes precedence.
    os.environ.setdefault("OPENAI_API_KEY", "sk-dummy-key")
    memory = Memory.from_config(mem0_config)
    audit_info(
        "memory.ltm",
        "mem0_init",
        provider="qdrant",
        collection=mem0_config["vector_store"]["config"]["collection_name"],
        embedding_model=mem0_config["embedder"]["config"]["model"],
        dims=768,
    )
except Exception as e:
    logger.warning("Failed to initialize Mem0/Qdrant connection: %s", e)
    audit_warn(
        "memory.ltm",
        "mem0_init_failed",
        reason=str(e)[:120],
        host=mem0_config["vector_store"]["config"]["host"],
    )
    memory = None
finally:
    # Clean up the dummy key so it doesn't leak to other OpenAI SDK usage
    if os.environ.get("OPENAI_API_KEY") == "sk-dummy-key":
        os.environ.pop("OPENAI_API_KEY", None)
