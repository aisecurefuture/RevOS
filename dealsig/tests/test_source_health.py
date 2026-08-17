"""Health and change-detection behaviour for the source connectors.

The bug these cover: every calendar_monitor reported "healthy" while producing
nothing and detecting nothing, because the page hash was stored but never
compared. A broken source and a working monitor looked identical.
"""

import pytest

from app.models import SourceStatus
from app.services import refresh as refresh_module
from app.services.refresh import ensure_sources, refresh_source
from app.services.sources import FetchResult, ParsedListing


def listing(external_id: str = "abc") -> ParsedListing:
    return ParsedListing(
        external_id=external_id,
        title="A property",
        source_url="https://example.gov/listing/1",
    )


@pytest.fixture
def stub_fetch(monkeypatch):
    """Swap the network call for a scripted result."""

    def install(result: FetchResult):
        monkeypatch.setattr(refresh_module, "fetch_source", lambda definition, etag="": result)

    return install


def test_monitor_reports_monitoring_not_healthy(db_session, stub_fetch):
    """A monitor produces no listings by design; it must not read as a live feed."""
    ensure_sources(db_session)
    stub_fetch(FetchResult(records=[], content_hash="hash-one"))
    refresh_source(db_session, "lake_county")
    status = db_session.get(SourceStatus, "lake_county")
    assert status.health == "monitoring"
    assert status.records_found == 0


def test_feed_that_parses_nothing_is_degraded(db_session, stub_fetch):
    """A 200 response with zero parsed listings means the parser broke."""
    ensure_sources(db_session)
    stub_fetch(FetchResult(records=[], content_hash="hash-one"))
    refresh_source(db_session, "gsa")
    status = db_session.get(SourceStatus, "gsa")
    assert status.health == "degraded"
    assert "produced no listings" in status.last_error


def test_feed_with_records_is_healthy(db_session, stub_fetch):
    ensure_sources(db_session)
    stub_fetch(FetchResult(records=[listing()], content_hash="hash-one"))
    refresh_source(db_session, "gsa")
    status = db_session.get(SourceStatus, "gsa")
    assert status.health == "healthy"
    assert status.last_error == ""


def test_not_modified_does_not_degrade_a_feed(db_session, stub_fetch):
    """304 means nothing changed, which is success — not a broken parser."""
    ensure_sources(db_session)
    stub_fetch(FetchResult(records=[], content_hash="", not_modified=True))
    refresh_source(db_session, "gsa")
    assert db_session.get(SourceStatus, "gsa").health == "healthy"


def test_first_fetch_is_not_reported_as_a_change(db_session, stub_fetch):
    """Nothing to compare against yet, so this must not fire a change event."""
    ensure_sources(db_session)
    stub_fetch(FetchResult(records=[], content_hash="hash-one"))
    run = refresh_source(db_session, "lake_county")
    assert run.changed is False
    assert db_session.get(SourceStatus, "lake_county").last_change_at is None


def test_changed_page_is_detected(db_session, stub_fetch):
    ensure_sources(db_session)
    stub_fetch(FetchResult(records=[], content_hash="hash-one"))
    refresh_source(db_session, "lake_county")

    stub_fetch(FetchResult(records=[], content_hash="hash-two"))
    run = refresh_source(db_session, "lake_county")

    assert run.changed is True
    status = db_session.get(SourceStatus, "lake_county")
    assert status.last_change_at is not None
    assert status.content_hash == "hash-two"


def test_unchanged_page_does_not_fire(db_session, stub_fetch):
    ensure_sources(db_session)
    stub_fetch(FetchResult(records=[], content_hash="hash-one"))
    refresh_source(db_session, "lake_county")
    first = db_session.get(SourceStatus, "lake_county").last_change_at

    run = refresh_source(db_session, "lake_county")
    assert run.changed is False
    assert db_session.get(SourceStatus, "lake_county").last_change_at == first


def test_fetch_failure_still_degrades(db_session, monkeypatch):
    ensure_sources(db_session)

    def boom(definition, etag=""):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(refresh_module, "fetch_source", boom)
    run = refresh_source(db_session, "lake_county")
    status = db_session.get(SourceStatus, "lake_county")
    assert run.status == "failed"
    assert status.health == "degraded"
    assert status.consecutive_failures == 1
