"""Settings from environment. Nothing secret has a default."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env", ".env"), extra="ignore")

    database_url: str = "sqlite:///./raqib.db"
    clips_dir: str = "./clips"
    cors_origins: str = "http://localhost:3000"

    agent_backend: str = "dryrun"  # dryrun | claude
    anthropic_api_key: str | None = None
    agent_model: str = "claude-sonnet-4-6"
    weekly_model: str = "claude-opus-4-1"

    greenlam_url: str | None = None
    greenlam_employee_id: str | None = None
    greenlam_pin: str | None = None
    alert_webhook_url: str | None = None

    default_site: str = "raqib_demo_store"

    # ---- v2: zero-cost LLM providers ----
    llm_provider: str = "ollama"  # ollama | gemini | groq | claude ; the first link of the chain
    llm_provider_order: str = "ollama,gemini,groq"  # free fallback order; claude is never implied
    llm_provider_route: str | None = None  # per-task overrides (a single provider name or a comma list)
    llm_provider_answer: str | None = None
    llm_provider_caption: str | None = None
    llm_provider_opinion: str | None = None
    llm_provider_judge: str | None = None
    llm_timeout_s: float = 90.0

    ollama_host: str = "http://localhost:11434"
    ollama_model_route: str = "qwen3:4b-instruct"
    ollama_model_answer: str = "qwen3:8b"
    ollama_model_judge: str = "qwen3:8b"
    ollama_model_caption: str = "qwen2.5vl:7b"
    ollama_model_opinion: str = "qwen2.5vl:7b"

    gemini_api_key: str | None = None
    gemini_model_text: str = "gemini-2.5-flash"
    gemini_model_route: str = "gemini-2.5-flash-lite"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.1-8b-instant"

    # daily request caps, kept below the published free tiers (docs/models.md); 0 disables a provider
    ollama_daily_requests: int = 5000
    gemini_daily_requests: int = 800
    groq_daily_requests: int = 800
    claude_daily_requests: int = 0
    llm_rpm: int = 10  # per-provider minute bucket

    # ---- v2: embeddings ----
    embed_dim: int = 1024  # dimension of Chunk.embedding; set once from the Task 24b spike
    embed_model: str = "ollama:bge-m3:567m"  # ollama:<tag> | fastembed:<name> | gemini:<model> | fake:<dim>
    rerank_enabled: bool = False
    docs_dir: str = "./documents"
    caption_min_severity: int = 2
    caption_max_frames: int = 3
    caption_daily_requests: int = 200

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
