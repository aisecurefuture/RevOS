"""Social platform adapters.

NO scraping. Each adapter publishes only via the platform's official API and
only when credentials are configured. When they are not, ``publish`` returns a
**draft outcome** — the caption/hashtags are copy-paste ready for manual
posting. Live auto-posting requires completing ``_publish_live`` with valid
OAuth tokens (each platform needs its own app review); that path is scaffolded
but intentionally not faked.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings


@dataclass
class PublishOutcome:
    published: bool
    mode: str          # "live" | "draft" | "live_unconfigured"
    message: str
    external_id: str | None = None


class SocialAdapter:
    platform = "base"

    def is_configured(self) -> bool:
        return False

    def publish(self, *, caption: str | None, media_urls: list[str],
                hashtags: list[str]) -> PublishOutcome:
        if not self.is_configured():
            return PublishOutcome(
                published=False, mode="draft",
                message=f"{self.platform}: no API credentials — copy-paste ready draft.",
            )
        return self._publish_live(caption=caption, media_urls=media_urls, hashtags=hashtags)

    def _publish_live(self, *, caption, media_urls, hashtags) -> PublishOutcome:
        # Implement the official API call here once OAuth tokens are configured.
        return PublishOutcome(
            published=False, mode="live_unconfigured",
            message=(f"{self.platform}: credentials present but live publishing is not "
                     "enabled in this build. Complete the adapter's API call to go live."),
        )


class LinkedInAdapter(SocialAdapter):
    platform = "linkedin"

    def is_configured(self) -> bool:
        return bool(settings.linkedin_client_id and settings.linkedin_client_secret)


class MetaInstagramAdapter(SocialAdapter):
    platform = "instagram"

    def is_configured(self) -> bool:
        return bool(settings.meta_page_access_token and settings.instagram_business_account_id)


class FacebookAdapter(SocialAdapter):
    platform = "facebook"

    def is_configured(self) -> bool:
        return bool(settings.meta_page_access_token)


class TwitterAdapter(SocialAdapter):
    platform = "twitter"

    def is_configured(self) -> bool:
        return bool(settings.twitter_bearer_token)


class YouTubeAdapter(SocialAdapter):
    platform = "youtube"

    def is_configured(self) -> bool:
        return bool(settings.youtube_api_key)


class TikTokAdapter(SocialAdapter):
    # No public auto-post API for general use — always draft (manual posting).
    platform = "tiktok"


_ADAPTERS: dict[str, SocialAdapter] = {
    "linkedin": LinkedInAdapter(),
    "instagram": MetaInstagramAdapter(),
    "facebook": FacebookAdapter(),
    "twitter": TwitterAdapter(),
    "youtube": YouTubeAdapter(),
    "tiktok": TikTokAdapter(),
}


def get_adapter(platform: str) -> SocialAdapter:
    return _ADAPTERS.get(platform, SocialAdapter())


def adapter_status() -> dict[str, bool]:
    """Which platforms have live credentials (for the dashboard)."""
    return {name: adapter.is_configured() for name, adapter in _ADAPTERS.items()}
