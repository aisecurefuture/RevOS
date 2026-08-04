from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "DealSig AI"
    app_env: Literal["development", "test", "production"] = "development"
    base_url: str = "http://localhost:8080"
    database_url: str = "sqlite:///./dealsig.db"
    session_secret: str = "development-only-change-this-to-32-random-characters"  # noqa: S105
    cookie_secure: bool = False
    cookie_same_site: Literal["lax", "strict", "none"] = "lax"
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    demo_mode: bool = True
    billing_bypass: bool = True
    seed_demo_data: bool = True
    refresh_interval_minutes: int = Field(default=15, ge=5, le=1440)
    http_timeout_seconds: int = Field(default=20, ge=3, le=60)
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id: str = ""
    market_data_api_key: str = ""
    market_data_api_url: str = ""
    sentry_dsn: str = ""
    resend_api_key: str = ""
    resend_from_email: str = "DealSig AI <access@dealsig.ai>"
    auth_code_ttl_minutes: int = Field(default=10, ge=5, le=30)
    google_client_id: str = ""
    google_client_secret: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    apple_client_id: str = ""
    apple_client_secret: str = ""
    passkey_rp_id: str = "localhost"
    passkey_origin: str = "http://localhost:8080"

    @field_validator("session_secret")
    @classmethod
    def validate_secret(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("SESSION_SECRET must be at least 32 characters")
        return value

    @property
    def host_list(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    def validate_production(self) -> None:
        if self.app_env != "production":
            return
        unsafe = []
        if self.session_secret.startswith("development-only"):
            unsafe.append("SESSION_SECRET")
        if not self.cookie_secure:
            unsafe.append("COOKIE_SECURE")
        if self.demo_mode:
            unsafe.append("DEMO_MODE")
        if self.billing_bypass:
            unsafe.append("BILLING_BYPASS")
        if not self.resend_api_key or not self.resend_from_email:
            unsafe.append("Resend configuration")
        if self.apple_client_id and self.cookie_same_site != "none":
            unsafe.append("COOKIE_SAME_SITE must be none for Apple's form_post callback")
        if not self.passkey_origin.startswith("https://"):
            unsafe.append("PASSKEY_ORIGIN")
        if unsafe:
            raise RuntimeError(f"Unsafe production configuration: {', '.join(unsafe)}")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production()
    return settings
