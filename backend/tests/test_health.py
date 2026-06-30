"""Smoke tests for the application scaffold (Module 1)."""

from __future__ import annotations


def test_liveness(client):
    resp = client.get("/health/live")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app"] == "RevOS"


def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "RevOS"


def test_security_headers_present(client):
    resp = client.get("/health/live")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in resp.headers


def test_docs_available_in_dev(client):
    # Non-production env should expose interactive docs.
    assert client.get("/docs").status_code == 200
