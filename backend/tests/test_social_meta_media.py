"""Facebook + Instagram media publishing (Phase 2). Graph API mocked."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.core.exceptions import RevOSError
from app.services.social import meta as meta_client

GRAPH = "https://graph.facebook.com/v21.0"


# ---------------------------------------------------------------------------
# Facebook (byte push)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fb_single_photo_publishes_directly():
    with respx.mock(base_url=GRAPH) as mock:
        mock.post("/page-1/photos").mock(return_value=httpx.Response(
            200, json={"id": "photo-1", "post_id": "page-1_99"}))
        res = await meta_client.publish_photos_to_page(
            "page-1", "tok", [b"\xff\xd8img"], caption="hi")
    assert res.external_id == "page-1_99"


@pytest.mark.asyncio
async def test_fb_multi_photo_uploads_unpublished_then_feeds():
    with respx.mock(base_url=GRAPH) as mock:
        mock.post("/page-1/photos").mock(return_value=httpx.Response(200, json={"id": "ph"}))
        feed = mock.post("/page-1/feed").mock(return_value=httpx.Response(200, json={"id": "page-1_150"}))
        res = await meta_client.publish_photos_to_page(
            "page-1", "tok", [b"a", b"b", b"c"], caption="gallery")
    assert res.external_id == "page-1_150"
    # attached_media carries all three uploaded photo ids (form-URL-encoded).
    from urllib.parse import parse_qs
    body = parse_qs(feed.calls.last.request.content.decode())
    assert body["attached_media"][0].count("media_fbid") == 3


@pytest.mark.asyncio
async def test_fb_video_uses_videos_endpoint():
    with respx.mock(base_url=GRAPH) as mock:
        videos = mock.post("/page-1/videos").mock(return_value=httpx.Response(200, json={"id": "vid-7"}))
        res = await meta_client.publish_video_to_page("page-1", "tok", b"movie", caption="tour")
    assert res.external_id == "vid-7"
    # The multipart part must carry a real filename+MIME, else Graph rejects a
    # valid MP4 as "unsupported format".
    body = videos.calls.last.request.content
    assert b'filename="video.mp4"' in body
    assert b"video/mp4" in body


@pytest.mark.asyncio
async def test_fb_video_honors_content_type():
    with respx.mock(base_url=GRAPH) as mock:
        videos = mock.post("/page-1/videos").mock(return_value=httpx.Response(200, json={"id": "v"}))
        await meta_client.publish_video_to_page("page-1", "tok", b"mov", caption="", content_type="video/quicktime")
    body = videos.calls.last.request.content
    assert b'filename="video.mov"' in body
    assert b"video/quicktime" in body


# ---------------------------------------------------------------------------
# Instagram (Meta fetches by public URL)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ig_single_image():
    with respx.mock(base_url=GRAPH) as mock:
        mock.post("/ig-1/media").mock(return_value=httpx.Response(200, json={"id": "cont-1"}))
        mock.post("/ig-1/media_publish").mock(return_value=httpx.Response(200, json={"id": "ig-post-1"}))
        res = await meta_client.publish_to_instagram(
            "ig-1", "tok", image_urls=["https://x/a.jpg"], caption="home")
    assert res.external_id == "ig-post-1"


@pytest.mark.asyncio
async def test_ig_carousel_creates_children_then_container():
    with respx.mock(base_url=GRAPH) as mock:
        media = mock.post("/ig-1/media")
        media.side_effect = [
            httpx.Response(200, json={"id": "child-1"}),
            httpx.Response(200, json={"id": "child-2"}),
            httpx.Response(200, json={"id": "carousel"}),
        ]
        mock.post("/ig-1/media_publish").mock(return_value=httpx.Response(200, json={"id": "ig-carousel-post"}))
        res = await meta_client.publish_to_instagram(
            "ig-1", "tok", image_urls=["https://x/a.jpg", "https://x/b.jpg"], caption="two")
    assert res.external_id == "ig-carousel-post"
    assert media.call_count == 3


@pytest.mark.asyncio
async def test_ig_reel_polls_status_until_finished(monkeypatch):
    async def _no_sleep(_s):
        return None
    monkeypatch.setattr(meta_client.asyncio, "sleep", _no_sleep)
    with respx.mock(base_url=GRAPH) as mock:
        mock.post("/ig-1/media").mock(return_value=httpx.Response(200, json={"id": "reel-cont"}))
        mock.get("/reel-cont").mock(return_value=httpx.Response(200, json={"status_code": "FINISHED"}))
        mock.post("/ig-1/media_publish").mock(return_value=httpx.Response(200, json={"id": "ig-reel-post"}))
        res = await meta_client.publish_to_instagram(
            "ig-1", "tok", video_url="https://x/v.mp4", caption="reel")
    assert res.external_id == "ig-reel-post"


@pytest.mark.asyncio
async def test_ig_reel_error_status_raises(monkeypatch):
    async def _no_sleep(_s):
        return None
    monkeypatch.setattr(meta_client.asyncio, "sleep", _no_sleep)
    with respx.mock(base_url=GRAPH) as mock:
        mock.post("/ig-1/media").mock(return_value=httpx.Response(200, json={"id": "reel-cont"}))
        mock.get("/reel-cont").mock(return_value=httpx.Response(200, json={"status_code": "ERROR"}))
        with pytest.raises(RevOSError) as exc:
            await meta_client.publish_to_instagram("ig-1", "tok", video_url="https://x/v.mp4", caption="x")
    assert exc.value.code == "ig_media_failed"


# ---------------------------------------------------------------------------
# Signed public media route
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_public_media_route_serves_signed_key(api, make_user):
    from app.models.user import Role
    r = await api.post("/api/auth/login", json=(await make_user("m@t.com", "AdminPass123", Role.admin)))
    h = {"X-CSRF-Token": r.json()["csrf_token"]}
    bid = (await api.post("/api/brands", headers=h, json={"name": "B"})).json()["id"]
    up = await api.post("/api/social/upload-media", headers=h, data={"brand_id": bid},
                        files={"file": ("p.jpg", b"\xff\xd8\xff\xd9pixels", "image/jpeg")})
    key = up.json()["media_url"]

    from app.services import social_connection_service as scs
    url = scs.public_media_url(key)
    token = url.rsplit("/", 1)[1]
    got = await api.get(f"/api/public/social-media/{token}")
    assert got.status_code == 200
    assert got.content == b"\xff\xd8\xff\xd9pixels"
    assert got.headers["content-type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_public_media_route_rejects_tampered_token(api):
    got = await api.get("/api/public/social-media/not-a-real-token")
    assert got.status_code == 404
