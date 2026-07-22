"""Per-platform audience-stats fetch functions (Phase 6 — live ingestion)."""

from __future__ import annotations

import httpx
import pytest
import respx
from app.services.social import linkedin as linkedin_client
from app.services.social import meta as meta_client
from app.services.social import threads as threads_client
from app.services.social import tiktok as tiktok_client
from app.services.social import x as x_client
from app.services.social import youtube as youtube_client

GRAPH = "https://graph.facebook.com/v21.0"
YT = "https://www.googleapis.com/youtube/v3"
TT = "https://open.tiktokapis.com/v2"
XAPI = "https://api.twitter.com/2"
THREADS = "https://graph.threads.net/v1.0"


@pytest.mark.asyncio
async def test_meta_page_audience_stats():
    with respx.mock(base_url=GRAPH) as mock:
        mock.get("/PAGE").mock(return_value=httpx.Response(200, json={"fan_count": 1000}))
        mock.get("/PAGE/posts").mock(return_value=httpx.Response(200, json={"data": [
            {"like_count": 50, "comments_count": 10}, {"like_count": 30, "comments_count": 20},
        ]}))
        stats = await meta_client.get_page_audience_stats("PAGE", "tok")
    assert stats.follower_count == 1000
    assert stats.engagement_rate == pytest.approx((60 + 50) / 2 / 1000)
    assert stats.sample_size == 2


@pytest.mark.asyncio
async def test_meta_instagram_audience_stats():
    with respx.mock(base_url=GRAPH) as mock:
        mock.get("/IGUSER").mock(return_value=httpx.Response(200, json={"followers_count": 2000}))
        mock.get("/IGUSER/media").mock(return_value=httpx.Response(200, json={"data": [
            {"like_count": 100, "comments_count": 5},
        ]}))
        stats = await meta_client.get_instagram_audience_stats("IGUSER", "tok")
    assert stats.follower_count == 2000
    assert stats.engagement_rate == pytest.approx(105 / 2000)


@pytest.mark.asyncio
async def test_youtube_audience_stats_full_chain():
    with respx.mock(base_url=YT) as mock:
        mock.get("/channels").mock(return_value=httpx.Response(200, json={"items": [{
            "statistics": {"subscriberCount": "5000", "hiddenSubscriberCount": False},
            "contentDetails": {"relatedPlaylists": {"uploads": "UPLOADS"}},
        }]}))
        mock.get("/playlistItems").mock(return_value=httpx.Response(200, json={"items": [
            {"contentDetails": {"videoId": "v1"}}, {"contentDetails": {"videoId": "v2"}},
        ]}))
        mock.get("/videos").mock(return_value=httpx.Response(200, json={"items": [
            {"statistics": {"likeCount": "100", "commentCount": "10"}},
            {"statistics": {"likeCount": "200", "commentCount": "20"}},
        ]}))
        stats = await youtube_client.get_audience_stats("tok")
    assert stats.follower_count == 5000
    assert stats.engagement_rate == pytest.approx((110 + 220) / 2 / 5000)
    assert stats.sample_size == 2


@pytest.mark.asyncio
async def test_youtube_hidden_subscriber_count_returns_none():
    with respx.mock(base_url=YT) as mock:
        mock.get("/channels").mock(return_value=httpx.Response(200, json={"items": [{
            "statistics": {"subscriberCount": "5000", "hiddenSubscriberCount": True},
            "contentDetails": {"relatedPlaylists": {"uploads": "UPLOADS"}},
        }]}))
        stats = await youtube_client.get_audience_stats("tok")
    assert stats.follower_count is None
    assert stats.engagement_rate is None


@pytest.mark.asyncio
async def test_tiktok_audience_stats_no_engagement():
    with respx.mock(base_url=TT) as mock:
        mock.get("/user/info/").mock(return_value=httpx.Response(200, json={
            "data": {"user": {"open_id": "u1", "follower_count": 300}}}))
        stats = await tiktok_client.get_audience_stats("tok")
    assert stats.follower_count == 300
    assert stats.engagement_rate is None


@pytest.mark.asyncio
async def test_threads_audience_stats():
    with respx.mock(base_url=THREADS) as mock:
        mock.get("/USER/threads_insights").mock(return_value=httpx.Response(200, json={
            "data": [{"name": "followers_count", "total_value": {"value": 777}}]}))
        stats = await threads_client.get_audience_stats("USER", "tok")
    assert stats.follower_count == 777
    assert stats.engagement_rate is None


@pytest.mark.asyncio
async def test_threads_audience_stats_api_failure_returns_empty():
    with respx.mock(base_url=THREADS) as mock:
        mock.get("/USER/threads_insights").mock(return_value=httpx.Response(400, json={}))
        stats = await threads_client.get_audience_stats("USER", "tok")
    assert stats.follower_count is None


@pytest.mark.asyncio
async def test_x_audience_stats():
    with respx.mock(base_url=XAPI) as mock:
        mock.get("/users/me").mock(return_value=httpx.Response(200, json={
            "data": {"id": "u1", "public_metrics": {"followers_count": 10000}}}))
        mock.get("/users/u1/tweets").mock(return_value=httpx.Response(200, json={"data": [
            {"public_metrics": {"like_count": 100, "retweet_count": 20, "reply_count": 5}},
        ]}))
        stats = await x_client.get_audience_stats("tok")
    assert stats.follower_count == 10000
    assert stats.engagement_rate == pytest.approx(125 / 10000)


@pytest.mark.asyncio
async def test_linkedin_audience_stats_is_a_documented_noop():
    stats = await linkedin_client.get_audience_stats("tok")
    assert stats.follower_count is None
    assert stats.engagement_rate is None
