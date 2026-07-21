"""Threads publishing — container status-poll + text/media."""

from __future__ import annotations

from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from app.core.exceptions import RevOSError
from app.services.social import threads as t

GRAPH = "https://graph.threads.net/v1.0"


@pytest.mark.asyncio
async def test_publish_text_waits_for_container_then_publishes(monkeypatch):
    """The bug: publishing before the container is FINISHED 400s. Must poll
    status until ready first."""
    monkeypatch.setattr(t.asyncio, "sleep", AsyncMock())  # no real delay
    with respx.mock(base_url=GRAPH) as mock:
        mock.post("/USER/threads").mock(return_value=httpx.Response(200, json={"id": "cont-1"}))
        status = mock.get("/cont-1").mock(side_effect=[
            httpx.Response(200, json={"status": "IN_PROGRESS"}),
            httpx.Response(200, json={"status": "FINISHED"}),
        ])
        pub = mock.post("/USER/threads_publish").mock(return_value=httpx.Response(200, json={"id": "post-9"}))
        res = await t.publish_text("USER", "tok", "hello")
    assert res.external_id == "post-9"
    assert status.call_count == 2          # polled until FINISHED
    assert pub.called                       # only published after ready


@pytest.mark.asyncio
async def test_publish_media_video_uses_video_container(monkeypatch):
    monkeypatch.setattr(t.asyncio, "sleep", AsyncMock())
    with respx.mock(base_url=GRAPH) as mock:
        create = mock.post("/USER/threads").mock(return_value=httpx.Response(200, json={"id": "c2"}))
        mock.get("/c2").mock(return_value=httpx.Response(200, json={"status": "FINISHED"}))
        mock.post("/USER/threads_publish").mock(return_value=httpx.Response(200, json={"id": "vid-3"}))
        res = await t.publish_media("USER", "tok", text="cap", video_url="https://x/v.mp4")
    assert res.external_id == "vid-3"
    q = parse_qs(urlparse(str(create.calls.last.request.url)).query)
    assert q["media_type"] == ["VIDEO"]
    assert q["video_url"] == ["https://x/v.mp4"]
    assert q["text"] == ["cap"]


@pytest.mark.asyncio
async def test_publish_media_errors_on_container_error(monkeypatch):
    monkeypatch.setattr(t.asyncio, "sleep", AsyncMock())
    with respx.mock(base_url=GRAPH) as mock:
        mock.post("/USER/threads").mock(return_value=httpx.Response(200, json={"id": "c3"}))
        mock.get("/c3").mock(return_value=httpx.Response(200, json={"status": "ERROR", "error_message": "bad video"}))
        with pytest.raises(RevOSError) as exc:
            await t.publish_media("USER", "tok", text="x", video_url="https://x/v.mp4")
    assert exc.value.code == "threads_media_failed"
