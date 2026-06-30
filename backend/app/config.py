"""Application configuration.

All settings are loaded from environment variables (12-factor). Optional
integrations default to empty/disabled so the app boots and degrades
gracefully when a key is missing. Nothing secret is ever hardcoded.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Core ---------------------------------------------------------------
    app_env: Environment = "development"
    debug: bool = False
    app_name: str = "RevOS"
    app_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:3000"
    public_base_url: str = "http://localhost:8000"
    secret_key: str = Field(min_length=32)
    cors_origins: str = "http://localhost:3000"
    # Only trust X-Forwarded-For (rate-limit keying / audit IPs) behind a known
    # reverse proxy. Default false so client IPs cannot be spoofed.
    trust_proxy: bool = False

    # --- Database / cache ---------------------------------------------------
    database_url: str = "postgresql+asyncpg://revos:revos@localhost:5432/revos"
    redis_url: str = "redis://localhost:6379/0"

    # --- Auth ---------------------------------------------------------------
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    jwt_algorithm: str = "HS256"
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    login_rate_limit: str = "5/minute"
    # Rate-limit storage backend. Empty => use redis_url (prod). Tests set
    # this to "memory://" for hermetic, dependency-free runs.
    rate_limit_storage_uri: str = ""
    # Password policy.
    password_min_length: int = 12
    password_max_length: int = 128

    owner_email: str = "owner@example.com"
    # Placeholder default; the real value comes from OWNER_PASSWORD env at seed.
    owner_password: str = "change-me"  # noqa: S105 — not a secret, overridden by env
    owner_name: str = "Owner"

    # --- Email (Resend) -----------------------------------------------------
    resend_api_key: str = ""
    resend_webhook_secret: str = ""   # Svix "whsec_..." for status webhooks
    email_test_mode: bool = True
    default_from_email: str = "no-reply@example.com"
    default_from_name: str = "RevOS"

    # --- AI -----------------------------------------------------------------
    ai_provider: Literal["anthropic", "openai", "local", "none"] = "none"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    local_ai_base_url: str = ""
    ai_rate_limit: str = "20/minute"

    # --- Payments -----------------------------------------------------------
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_publishable_key: str = ""

    # --- Storage ------------------------------------------------------------
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_dir: str = "./storage"
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_region: str = "us-east-1"

    # --- Analytics ----------------------------------------------------------
    plausible_domain: str = ""
    plausible_api_key: str = ""
    posthog_api_key: str = ""
    posthog_host: str = "https://us.i.posthog.com"
    ga_measurement_id: str = ""

    # --- Social adapters ----------------------------------------------------
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_page_access_token: str = ""
    instagram_business_account_id: str = ""
    twitter_bearer_token: str = ""
    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    youtube_api_key: str = ""

    # --- Low-cost integrations ----------------------------------------------
    calendly_api_key: str = ""
    bitly_access_token: str = ""
    google_sheets_credentials_json: str = ""
    notion_api_key: str = ""
    zapier_webhook_secret: str = ""

    # Hard ceiling on any request body (bytes). Above the media upload cap so
    # that route's own limit applies first; this is the global DoS backstop.
    max_request_bytes: int = 256 * 1024 * 1024

    # --- SSRF allowlist -----------------------------------------------------
    ssrf_allowed_hosts: str = ""

    # --- Derived helpers ----------------------------------------------------
    @field_validator("secret_key")
    @classmethod
    def _reject_default_secret(cls, v: str) -> str:
        if v.strip().lower() in {"", "change-me", "change-me-generate-a-long-random-value"}:
            # Allowed in dev so the app boots, but make the risk loud.
            import warnings

            warnings.warn(
                "SECRET_KEY is unset or default — generate a strong value before production.",
                stacklevel=2,
            )
        return v

    @model_validator(mode="after")
    def _enforce_production_security(self):
        """Hard-fail on insecure settings in production (fail closed)."""
        if self.app_env != "production":
            return self
        problems = []
        if self.secret_key.strip().lower() in {
            "change-me", "change-me-generate-a-long-random-value",
        }:
            problems.append("SECRET_KEY must be a generated random value")
        if self.debug:
            problems.append("DEBUG must be false")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true (HTTPS)")
        if self.cookie_samesite == "none" and not self.cookie_secure:
            problems.append("COOKIE_SAMESITE=none requires COOKIE_SECURE=true")
        if problems:
            raise ValueError("Insecure production config: " + "; ".join(problems))
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def ssrf_allowed_host_list(self) -> list[str]:
        return [h.strip().lower() for h in self.ssrf_allowed_hosts.split(",") if h.strip()]

    @property
    def effective_rate_limit_storage(self) -> str:
        """Rate-limit backend: explicit override, else Redis."""
        return self.rate_limit_storage_uri or self.redis_url

    @property
    def sync_database_url(self) -> str:
        """Sync SQLAlchemy URL for Alembic / Celery (asyncpg -> psycopg2)."""
        return self.database_url.replace("+asyncpg", "").replace(
            "postgresql://", "postgresql+psycopg2://", 1
        )

    @property
    def email_enabled(self) -> bool:
        """True only when Resend is configured AND test mode is off."""
        return bool(self.resend_api_key) and not self.email_test_mode

    @property
    def ai_enabled(self) -> bool:
        if self.ai_provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.ai_provider == "openai":
            return bool(self.openai_api_key)
        if self.ai_provider == "local":
            return bool(self.local_ai_base_url)
        return False

    def integration_status(self) -> dict[str, bool]:
        """Snapshot of which optional integrations are configured.

        Used by the dashboard/health endpoints so the UI can show what is
        live vs. running in fallback (draft / mock) mode.
        """
        return {
            "resend": bool(self.resend_api_key),
            "email_live": self.email_enabled,
            "ai": self.ai_enabled,
            "stripe": bool(self.stripe_secret_key),
            "s3": self.storage_backend == "s3" and bool(self.s3_bucket),
            "plausible": bool(self.plausible_domain),
            "posthog": bool(self.posthog_api_key),
            "ga": bool(self.ga_measurement_id),
            "linkedin": bool(self.linkedin_client_id),
            "meta": bool(self.meta_page_access_token),
            "twitter": bool(self.twitter_bearer_token),
            "youtube": bool(self.youtube_api_key),
            "calendly": bool(self.calendly_api_key),
            "bitly": bool(self.bitly_access_token),
            "notion": bool(self.notion_api_key),
        }


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
