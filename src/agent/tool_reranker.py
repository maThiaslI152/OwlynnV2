import logging
import numpy as np
from openai import OpenAI
from src.config.config_loader import config

logger = logging.getLogger(__name__)

_openai_client = None

def get_openai_client():
    global _openai_client
    if _openai_client is None:
        try:
            base_url = config.get("models.embedding.base_url", "http://127.0.0.1:1234/v1")
            _openai_client = OpenAI(base_url=base_url, api_key="lm-studio")
        except Exception as e:
            logger.error(f"Failed to create OpenAI client for embeddings: {e}")
    return _openai_client

def rerank_tools(query: str, tools: list, top_k: int = 15) -> list:
    if len(tools) <= top_k:
        return tools
    if not query:
        return tools[:top_k]

    client = get_openai_client()
    if not client:
        return tools[:top_k]

    try:
        tool_descriptions = [
            t.description if hasattr(t, "description") else str(t) for t in tools
        ]

        embed_model = config.get("models.embedding.model_name", "text-embedding-nomic-embed-text-v1.5-embedding")

        # Embed query and tools
        res_query = client.embeddings.create(
            input=[query], model=embed_model
        )
        query_emb = np.array(res_query.data[0].embedding)

        res_tools = client.embeddings.create(
            input=tool_descriptions,
            model=embed_model,
        )
        tool_embs = [np.array(d.embedding) for d in res_tools.data]

        # Cosine similarity
        query_norm = np.linalg.norm(query_emb)
        similarities = []
        for emb in tool_embs:
            norm = np.linalg.norm(emb)
            if query_norm == 0 or norm == 0:
                similarities.append(0.0)
            else:
                similarities.append(float(np.dot(query_emb, emb) / (query_norm * norm)))

        scored_tools = sorted(
            zip(tools, similarities), key=lambda x: x[1], reverse=True
        )
        return [t for t, s in scored_tools[:top_k]]
    except Exception as e:
        logger.error(f"Error reranking tools: {e}")
        return tools[:top_k]
