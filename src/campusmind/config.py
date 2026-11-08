"""Central configuration, explicit chat models, and embedding client."""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

# ---- app/core/config.py ----
class Settings(BaseSettings):
    """Central runtime configuration.

    The application intentionally has no production secrets or remote host addresses
    baked into source code. All environment-specific values come from `.env` or the
    process environment.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "CampusMind"
    app_version: str = "1.2.1"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",
        ]
    )
    auth_cookie_name: str = "campusmind_session"
    auth_session_ttl_hours: int = Field(default=168, ge=1, le=2160)
    auth_cookie_secure: bool = False

    infra_connect_timeout: float = Field(default=5.0, gt=0)

    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_db: str = "campusmind"
    postgres_user: str = "campusmind"
    postgres_password: str = ""
    postgres_pool_size: int = 5
    postgres_max_overflow: int = 10
    postgres_pool_timeout: int = 10

    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"

    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    rustfs_endpoint: str = "http://127.0.0.1:9000"
    rustfs_access_key: str = ""
    rustfs_secret_key: str = ""
    rustfs_region: str = "us-east-1"
    rustfs_bucket: str = "campusmind"

    rag_top_k_vector: int = Field(default=8, ge=1, le=100)
    rag_top_k_keyword: int = Field(default=8, ge=1, le=100)
    rag_top_k_final: int = Field(default=5, ge=1, le=20)
    rag_rrf_k: int = Field(default=60, ge=1, le=1000)

    rag_context_relative_threshold: float = Field(default=0.82, ge=0.0, le=1.0)
    rag_context_score_floor: float = Field(default=0.0, ge=0.0, le=1.0)
    rag_context_max_chunks: int = Field(default=3, ge=1, le=20)
    rag_context_min_chunks: int = Field(default=1, ge=1, le=20)

    rag_embedding_provider: str = "auto"
    rag_embedding_model: str = "text-embedding-v4"
    rag_embedding_dimensions: int = Field(default=1024, ge=8, le=8192)
    rag_embedding_base_url: str | None = None
    rag_embedding_api_key: str | None = None
    rag_embedding_batch_size: int = Field(default=10, ge=1, le=256)

    ingestion_max_file_mb: int = Field(default=30, ge=1, le=200)
    ingestion_chunk_max_chars: int = Field(default=1200, ge=200, le=8000)
    ingestion_chunk_overlap_chars: int = Field(default=120, ge=0, le=2000)
    ingestion_download_url_ttl_seconds: int = Field(default=900, ge=60, le=86400)

    @property
    def sqlalchemy_database_url(self) -> str:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()

# ---- app/core/env_utils.py ----
"""Legacy environment aliases used by a few deployment integrations.

New code should prefer :func:`campusmind.config.get_settings`.  The aliases remain
for compatibility with existing operator environments while avoiding `.env`
overrides of already-exported process variables.
"""



load_dotenv(override=False)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL")
LOCAL_BASE_URL = os.getenv("LOCAL_BASE_URL")

# ---- app/core/init_embedding.py ----
settings = get_settings()


def _resolved_embedding_endpoint() -> tuple[str | None, str | None]:
    return (
        settings.rag_embedding_base_url or DASHSCOPE_BASE_URL,
        settings.rag_embedding_api_key or DASHSCOPE_API_KEY,
    )


def resolved_embedding_provider() -> str:
    provider = settings.rag_embedding_provider.strip().lower()
    if provider == "auto":
        base_url, _ = _resolved_embedding_endpoint()
        return "openai_compatible" if base_url else "deterministic"
    return provider


def resolved_embedding_model_name() -> str:
    explicit = os.getenv("RAG_EMBEDDING_MODEL")
    if explicit:
        return explicit.strip()
    if DASHSCOPE_BASE_URL or settings.rag_embedding_base_url:
        return "text-embedding-v4"
    return "deterministic-char-ngram-v1"


def resolved_embedding_dimensions() -> int:
    explicit = os.getenv("RAG_EMBEDDING_DIMENSIONS")
    if explicit:
        return int(explicit)
    if resolved_embedding_provider() == "deterministic":
        return 384
    return settings.rag_embedding_dimensions


EMBEDDING_MODEL_NAME = resolved_embedding_model_name()
EMBEDDING_DIMENSIONS = resolved_embedding_dimensions()
EMBEDDING_PROVIDER_NAME = resolved_embedding_provider()


@lru_cache
def get_embedding_model() -> OpenAIEmbeddings:
    from langchain_openai import OpenAIEmbeddings

    provider = resolved_embedding_provider()
    if provider not in {"openai_compatible", "openai"}:
        raise RuntimeError(
            "Configured embedding model requested while the resolved embedding provider "
            "is not OpenAI-compatible"
        )

    base_url, api_key = _resolved_embedding_endpoint()
    if not base_url:
        raise RuntimeError("RAG_EMBEDDING_BASE_URL (or DASHSCOPE_BASE_URL) is required")

    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL_NAME,
        api_key=api_key,
        base_url=base_url,
        dimensions=EMBEDDING_DIMENSIONS,
        check_embedding_ctx_length=False,
        chunk_size=settings.rag_embedding_batch_size,
    )


class _LazyEmbeddingModel:
    def embed_documents(self, texts):
        return get_embedding_model().embed_documents(texts)

    def embed_query(self, text):
        return get_embedding_model().embed_query(text)

    def __getattr__(self, name):
        return getattr(get_embedding_model(), name)


embedding_model = _LazyEmbeddingModel()

# ---- app/core/init_llm.py ----
#
# CampusMind model switchboard.
#
# Changing the active chat model does NOT require editing .env.
# Keep secrets and endpoints in .env; keep model selection here in source code.
# To switch the whole system to DeepSeek, change only:
#
#     ACTIVE_LLM = "deepseek"
#
# To use the local Qwen model again:
#
#     ACTIVE_LLM = "qwen"
#
ACTIVE_LLM = "qwen"

# Endpoint / credential values remain environment-specific.
DEEPSEEK_API_KEY = DEEPSEEK_API_KEY or "not-configured"
DEEPSEEK_BASE_URL = DEEPSEEK_BASE_URL or "https://api.deepseek.com"
LOCAL_BASE_URL = LOCAL_BASE_URL or "http://127.0.0.1:3006/v1"

# OpenAI-compatible local servers commonly ignore the API key, but the
# OpenAI client validates that one exists.  This keeps local Qwen startup
# zero-config while still allowing OPENAI_API_KEY to override it.
if not os.getenv("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = "local"

# Keep model initialization intentionally explicit and easy to edit.
deepseek_llm = init_chat_model(
    model="deepseek-v4-flash",
    model_provider="deepseek",
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL,
    extra_body={
        "thinking": {"type": "disabled"}  # disable thinking mode
    },
)

qwen_llm = init_chat_model(
    model="qwen3-14b",
    model_provider="openai",
    base_url=LOCAL_BASE_URL,
    extra_body={
        "chat_template_kwargs": {
            "enable_thinking": False
        }
    },
)

def _model_name(model, fallback: str) -> str:
    return str(
        getattr(model, "model_name", None)
        or getattr(model, "model", None)
        or fallback
    )


_LLM_REGISTRY = {
    "deepseek": (deepseek_llm, _model_name(deepseek_llm, "deepseek-v4-flash"), "deepseek"),
    "qwen": (qwen_llm, _model_name(qwen_llm, "qwen3-14b"), "openai"),
}

if ACTIVE_LLM not in _LLM_REGISTRY:
    raise RuntimeError(
        f"Unsupported ACTIVE_LLM={ACTIVE_LLM!r}; choose one of {sorted(_LLM_REGISTRY)}"
    )

main_llm, MAIN_MODEL_NAME, LLM_PROVIDER_NAME = _LLM_REGISTRY[ACTIVE_LLM]


def resolved_llm_provider() -> str:
    """Return the provider for the code-selected active LLM."""
    return LLM_PROVIDER_NAME

