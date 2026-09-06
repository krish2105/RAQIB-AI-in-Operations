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

    # ---- v2: VLM second opinion (advisory; can raise attention, never lower severity) ----
    vlm_auto: bool = True  # auto-run for severity 3 and detector confidence < VLM_AUTO_MAX_CONF once a clip exists
    vlm_auto_max_conf: float = 0.6
    vlm_daily_requests: int = 100
    vlm_review_confidence: float = 0.8  # disagreement at or above this confidence asks a human to review

    # ---- v2: Crew (multi-agent with a security envelope) ----
    agents_enabled: bool = True  # global kill switch (env); POST /crew/kill flips the DB flag too
    crew_enabled: bool = True  # route events to the crew runtime; false = Phase B agent path only
    crew_hmac_secret: str = "dev-only-change-me"  # per-agent keys are derived from this; set in prod
    crew_max_tool_calls: int = 6
    crew_max_usd: float = 0.0  # zero-cost: any paid provider call breaches the budget
    crew_max_seconds: int = 60
    memory_protected_keys: str = "policy_thresholds,site_profile,escalation_roles"
    memory_max_value_chars: int = 2000
    memory_churn_per_hour: int = 30

    # ---- v2: auth and RBAC (Supabase Auth JWTs) ----
    auth_required: bool = False  # False: unauthenticated requests act as the dev admin (local dev, demo); True: JWT on every route
    supabase_url: str | None = None  # https://<ref>.supabase.co ; JWKS at /auth/v1/.well-known/jwks.json
    supabase_jwt_secret: str | None = None  # legacy HS256 secret; when set it is used instead of JWKS
    auth_admin_emails: str = ""  # comma list; these become admin on first login
    auth_default_role: str = "viewer"
    rate_ask_per_min: int = 20
    rate_vlm_per_min: int = 10

    # ---- v2: observability, retention, cost ----
    otel_exporter: str = "none"  # none | console | otlp ; spans are always recorded to llm_spans for the cost KPI
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "raqib-api"
    retention_clips_days: int = 30
    retention_events_days: int = 400
    retention_memories_days: int = 90
    retention_schedule: bool = True  # run the retention job daily inside the API process

    # ---- v2: fleet, drift, health ----
    drift_psi_threshold: float = 0.2
    drift_hours: int = 3  # consecutive hours over the threshold before a model_drift event
    drift_baseline_days: int = 7
    heartbeat_offline_s: int = 300

    # ---- v2: integrations ----
    whatsapp_phone_id: str | None = None
    whatsapp_token: str | None = None
    greenlam_retries: int = 3
    greenlam_breaker_failures: int = 3
    greenlam_breaker_cooldown_s: float = 60.0

    # ---- v2: Watch camera wall ----
    stream_upstream: str | None = None  # edge MJPEG base, e.g. http://edge-box.lan:8554 ; empty = tiles show detections only
    stream_token: str | None = None  # token the edge box requires; never exposed to the browser

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
