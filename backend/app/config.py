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
    # 2FA code entry throttle. Applied per-IP on setup/disable and, more
    # importantly, per-account on the 2FA login step (defeats IP rotation).
    twofa_rate_limit: str = "10/5minute"
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
    # Default model for the `local` provider (e.g. an Ollama tag like
    # "qwen2.5:7b"). Falls back to `openai_model` if unset.
    local_ai_model: str = ""
    # Optional per-use-case model overrides for the `local` provider, as a JSON
    # object env var, e.g. LOCAL_AI_MODEL_MAP='{"email":"qwen2.5:7b","social":"gemma2:9b"}'.
    # Keys are ai_service use-cases: email, social, landing, ideas, summary.
    local_ai_model_map: dict[str, str] = Field(default_factory=dict)
    ai_rate_limit: str = "20/minute"

    # --- Payments -----------------------------------------------------------
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_publishable_key: str = ""

    # Stripe Price IDs — create these in the Stripe dashboard, then set env vars.
    # Monthly prices
    stripe_pro_monthly_price_id: str = ""
    stripe_agency_monthly_price_id: str = ""
    # Annual prices (billed yearly, ~20% discount)
    stripe_pro_annual_price_id: str = ""
    stripe_agency_annual_price_id: str = ""

    # Display prices in cents (Stripe is authoritative for actual charges).
    plan_pro_monthly_cents: int = 14900      # $149.00
    plan_pro_annual_cents: int = 142800      # $1,428.00 ($119/mo)
    plan_agency_monthly_cents: int = 44900   # $449.00
    plan_agency_annual_cents: int = 430800   # $4,308.00 ($359/mo)

    # Trial length in days for new accounts.
    trial_days: int = 14

    # --- Secrets (OpenBao / Vault) ------------------------------------------
    bao_addr: str = "http://openbao:8200"
    bao_token: str = ""          # root or AppRole token; empty = Bao disabled
    bao_kv_mount: str = "secret" # KV v2 mount name

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
    linkedin_redirect_uri: str = ""  # e.g. https://api.revos360.com/api/social/linkedin/callback
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_redirect_uri: str = ""   # e.g. https://api.revos360.com/api/social/facebook/callback
    meta_page_access_token: str = ""
    instagram_business_account_id: str = ""
    threads_app_id: str = ""
    threads_app_secret: str = ""
    threads_redirect_uri: str = ""  # e.g. https://api.revos360.com/api/social/threads/callback
    twitter_bearer_token: str = ""
    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    # X (Twitter) OAuth 2.0 user-context client (Authorization Code + PKCE).
    # Distinct from the OAuth 1.0a api_key/secret above.
    twitter_client_id: str = ""
    twitter_client_secret: str = ""
    twitter_redirect_uri: str = ""  # e.g. https://api.revos360.com/api/social/twitter/callback
    youtube_api_key: str = ""
    # YouTube uses a Google Cloud OAuth 2.0 client (distinct from the read-only
    # youtube_api_key above). Needed for channel connect + video upload.
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_redirect_uri: str = ""  # e.g. https://api.revos360.com/api/social/youtube/callback
    # TikTok Login Kit + Content Posting API. Note: TikTok calls the id "client_key".
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_redirect_uri: str = ""  # e.g. https://api.revos360.com/api/social/tiktok/callback

    # Low-cost integrations (Calendly, Notion, Bitly, Zapier, Google Sheets) are
    # configured per-account from Settings → Integrations (see
    # IntegrationCredential / integration_credentials_service), not via env vars.

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
        }


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
