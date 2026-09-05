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

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
