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
    """Which platforms have their OAuth app configured on this server, so users
    can connect accounts on the Social Connections page.

    This reflects the M5/M6 OAuth integrations (app id/secret/redirect), NOT the
    legacy static-credential adapters above — those predate the OAuth flow and
    only remain for the (now unused) draft publish path. A ``True`` here means
    "connectable", not "an account is connected" — that lives per-account in the
    social_connections table.
    """
    meta = bool(settings.meta_app_id and settings.meta_app_secret and settings.meta_redirect_uri)
    return {
        "facebook": meta,
        "instagram": meta,
        "threads": bool(
            settings.threads_app_id and settings.threads_app_secret and settings.threads_redirect_uri
        ),
        "youtube": bool(
            settings.youtube_client_id and settings.youtube_client_secret and settings.youtube_redirect_uri
        ),
        "twitter": bool(
            settings.twitter_client_id and settings.twitter_client_secret and settings.twitter_redirect_uri
        ),
        "linkedin": bool(
            settings.linkedin_client_id and settings.linkedin_client_secret and settings.linkedin_redirect_uri
        ),
        "tiktok": False,  # no OAuth publishing integration yet
    }
