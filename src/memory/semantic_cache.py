"""Semantic Caching for repetitive queries using redisvl."""
import os
import logging
import asyncio

logger = logging.getLogger(__name__)

from src.config.config_loader import config
from src.config.settings import REDIS_URL

try:
    from redisvl.extensions.cache.llm import SemanticCache
    from redisvl.utils.vectorize.base import BaseVectorizer
    import redis.asyncio as redis
except ImportError:
    SemanticCache = None
    BaseVectorizer = object
    logger.warning("redisvl not available, Semantic Caching disabled.")

from openai import AsyncOpenAI
from typing import List

_embed_model = config.get(
    "models.embedding.model_name", "text-embedding-nomic-embed-text-v1.5-embedding"
)
_embed_url = config.get("models.embedding.base_url", "http://127.0.0.1:1234/v1")

from pydantic import PrivateAttr

class CustomOpenAIVectorizer(BaseVectorizer):
    dims: int = 768
    _client: AsyncOpenAI = PrivateAttr()

    def __init__(self, model: str, base_url: str):
        super().__init__(model=model)
        self._client = AsyncOpenAI(api_key="sk-dummy", base_url=base_url)
        
    def embed(self, text: str, **kwargs) -> List[float]:
        raise NotImplementedError()
        
    async def aembed(self, text: str, **kwargs) -> List[float]:
        response = await self._client.embeddings.create(input=[text], model=self.model)
        return response.data[0].embedding

    def embed_many(self, texts: List[str], **kwargs) -> List[List[float]]:
        raise NotImplementedError()
        
    async def aembed_many(self, texts: List[str], **kwargs) -> List[List[float]]:
        response = await self._client.embeddings.create(input=texts, model=self.model)
        return [d.embedding for d in response.data]

semantic_cache = None

async def init_semantic_cache():
    global semantic_cache
    if not SemanticCache:
        return
        
    try:
        # Override dummy key for OpenAI SDK since LM Studio doesn't check it
        os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
        
        vectorizer = CustomOpenAIVectorizer(
            model=_embed_model,
            base_url=_embed_url
        )
            
        redis_client = redis.from_url(REDIS_URL)

        semantic_cache = SemanticCache(
            name="owlynn_semantic_cache",
            distance_threshold=0.08, # 92% similarity threshold
            vectorizer=vectorizer,
            redis_url=REDIS_URL,
        )
        # Use the async client
        semantic_cache._async_redis_client = redis_client
        
        try:
            await semantic_cache.aindex()
        except Exception as e:
            if "Index already exists" not in str(e):
                logger.warning("Error creating semantic cache index: %s", e)
    except Exception as e:
        logger.warning("Failed to initialize Semantic Cache: %s", e)
        semantic_cache = None


async def check_semantic_cache(prompt: str, project_id: str = "default") -> str | None:
    if not semantic_cache:
        return None
    try:
        scoped_prompt = f"[Project: {project_id}] {prompt}"
        results = await semantic_cache.acheck(prompt=scoped_prompt)
        if results and len(results) > 0:
            return results[0]["response"]
    except Exception as e:
        logger.warning("Semantic Cache check failed: %s", e)
    return None


async def store_semantic_cache(prompt: str, response: str, project_id: str = "default"):
    if not semantic_cache:
        return
    try:
        scoped_prompt = f"[Project: {project_id}] {prompt}"
        await semantic_cache.astore(prompt=scoped_prompt, response=response)
    except Exception as e:
        logger.warning("Semantic Cache store failed: %s", e)

if __name__ == "__main__":
    async def test():
        await init_semantic_cache()
        await store_semantic_cache("Hello world", "Hi there!", project_id="test")
        res = await check_semantic_cache("Hello world", project_id="test")
        print("Result:", res)
    asyncio.run(test())
