"""
Global project settings and configuration.

Delegates to the centralized config_loader (defaults.yaml → env → profile)
while preserving backward-compatible module-level constants.
"""

import os
from pathlib import Path

from src.config.config_loader import config, get_m4_optimization

# ── Base Paths ───────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = Path(os.getenv("OWLYNN_DATA_DIR", PROJECT_ROOT / "data"))
WORKSPACE_DIR = Path(os.getenv("OWLYNN_WORKSPACE_DIR", PROJECT_ROOT / "workspace"))
MODELS_DIR = PROJECT_ROOT / ".models"


def normalize_project_id(project_id: str | None) -> str:
    if project_id is None:
        return "default"
    s = str(project_id).strip()
    if not s or s.lower() in ("null", "undefined"):
        return "default"
    return s


def get_project_workspace(project_id: str | None = None) -> str:
    pid = normalize_project_id(project_id)
    path = WORKSPACE_DIR / "projects" / pid
    path.mkdir(parents=True, exist_ok=True)
    return str(path.resolve())


# ── Server Settings ──────────────────────────────────────────────────────────

HOST = config.get("server.host", "127.0.0.1")
PORT = int(config.get("server.port", 8000))

# ── External Services ────────────────────────────────────────────────────────

QDRANT_HOST = config.get("external_services.qdrant.host", "localhost")
QDRANT_PORT = int(config.get("external_services.qdrant.port", 6333))

# ── MCP Settings ─────────────────────────────────────────────────────────────

MCP_CONFIG_PATH = PROJECT_ROOT / "mcp_config.json"

# ── Web RAG ──────────────────────────────────────────────────────────────────

WEB_RAG_ENABLED = config.get("web_rag.enabled", True)
WEB_RAG_EMBED_MODEL = config.get(
    "web_rag.embed_model", "text-embedding-nomic-embed-text-v1.5-embedding"
)
WEB_RAG_TOP_K = int(config.get("web_rag.top_k", 5))
WEB_RAG_CHUNK_CHARS = int(config.get("web_rag.chunk_chars", 720))
WEB_RAG_CHUNK_OVERLAP = int(config.get("web_rag.chunk_overlap", 120))
WEB_RAG_MIN_CHARS_FOR_RANK = int(config.get("web_rag.min_chars_for_rank", 1800))
WEB_SEARCH_RERANK_TOP_N = int(config.get("web_rag.rerank_top_n", 8))

# ── Web Search ───────────────────────────────────────────────────────────────

WEB_SEARCH_TIMEOUT_SECONDS = float(config.get("web_search.timeout_seconds", 22))
WEB_SEARCH_ENABLE_CURL_CFFI = config.get("web_search.enable_curl_cffi", True)
WEB_SEARCH_ENABLE_BROWSER_FALLBACK = config.get(
    "web_search.enable_browser_fallback", True
)

# ── SearXNG ──────────────────────────────────────────────────────────────────

SEARXNG_URL = config.get("external_services.searxng.url", "") or ""

# ── Redis & DeepSeek ─────────────────────────────────────────────────────────

REDIS_URL = config.get("external_services.redis.url", "redis://localhost:6379")
DEEPSEEK_API_KEY = (os.getenv("DEEPSEEK_API_KEY", "") or "").strip()
VOICE_WAKE_WORD = (os.getenv("VOICE_WAKE_WORD", "Athena") or "Athena").strip()
VOICE_AUTO_TTS = os.getenv("VOICE_AUTO_TTS", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# ── Context Windows ──────────────────────────────────────────────────────────

MEDIUM_DEFAULT_CONTEXT = int(config.get("models.medium.context_window"))
MEDIUM_LONGCTX_CONTEXT = int(
    config.get("models.medium.context_window")  # longctx variant no longer exists
)
CLOUD_CONTEXT = int(config.get("models.cloud.context_window"))

# ── M4 Mac Optimization ──────────────────────────────────────────────────────

M4_MAC_OPTIMIZATION = get_m4_optimization()

# ── Model Timeouts & Tokens (M4 vs standard) ─────────────────────────────────

if (
    os.getenv("MACHINE_TYPE") == "M4_MAC"
    or os.getenv("OPTIMIZE_FOR_M4", "").lower() == "true"
):
    MODEL_TIMEOUT_SMALL = M4_MAC_OPTIMIZATION["small_model"]["timeout"]
    MODEL_TIMEOUT_MEDIUM = M4_MAC_OPTIMIZATION["medium_model"]["timeout"]
    MAX_TOKENS_SMALL = M4_MAC_OPTIMIZATION["small_model"]["max_tokens"]
    MAX_TOKENS_MEDIUM = M4_MAC_OPTIMIZATION["medium_model"]["max_tokens"]
    MAX_MEMORIES = M4_MAC_OPTIMIZATION["memory"]["max_facts"]
    MEMORY_SEARCH_WINDOW = M4_MAC_OPTIMIZATION["memory"]["search_window"]
else:
    MODEL_TIMEOUT_SMALL = int(
        config.get("models.small.timeout")
        or config.get("models.standard.small.timeout")
        or 15
    )
    MODEL_TIMEOUT_MEDIUM = int(
        config.get("models.medium.timeout")
        or config.get("models.standard.medium.timeout")
        or 90
    )
    MAX_TOKENS_SMALL = int(
        config.get("models.small.max_tokens")
        or config.get("models.standard.small.max_tokens")
        or 2048
    )
    MAX_TOKENS_MEDIUM = int(
        config.get("models.medium.max_tokens")
        or config.get("models.standard.medium.max_tokens")
        or 16384
    )
    MAX_MEMORIES = int(config.get("memory.max_facts") or 200)
    MEMORY_SEARCH_WINDOW = int(config.get("memory.search_window") or 50)

# ── Ensure directories exist ─────────────────────────────────────────────────

DATA_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
