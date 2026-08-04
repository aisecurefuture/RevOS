import re

from bs4 import BeautifulSoup
from sqlalchemy import select

from app.database import SessionLocal
from app.models import User


def csrf_from(response) -> str:
    match = re.search(r'name="csrf-token" content="([^"]+)"', response.text)
    assert match
    return match.group(1)


def demo_code_from(response) -> str:
    match = re.search(r'<strong>(\d{6})</strong>', response.text)
    assert match
    return match.group(1)


def request_code(client, email="member@example.com", next_path="/app"):
    page = client.get("/login")
    return client.post(
        "/auth/code/request",
        data={"csrf_token": csrf_from(page), "email": email, "next": next_path},
    )


def test_security_headers_and_brand_assets(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.get("/brand-logo.png").headers["content-type"] == "image/png"
    assert client.get("/brand-logo-dark.png").headers["content-type"] == "image/png"


def test_csrf_blocks_forged_code_request(client):
    response = client.post("/auth/code/request", data={"email": "member@example.com"})
    assert response.status_code == 403


def test_email_code_creates_verified_passwordless_session(client):
    requested = request_code(client)
    code = demo_code_from(requested)
    response = client.post(
        "/auth/code/verify",
        data={
            "csrf_token": csrf_from(requested),
            "email": "member@example.com",
            "code": code,
            "next": "/app",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Highest deal signals" in client.get("/app").text
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "member@example.com"))
        assert user is not None
        assert user.email_verified_at is not None


def test_resend_invalidates_the_previous_code(client):
    first = request_code(client, "resend@example.com")
    first_code = demo_code_from(first)
    second = client.post(
        "/auth/code/request",
        data={
            "csrf_token": csrf_from(first),
            "email": "resend@example.com",
            "next": "/app",
        },
    )
    old_result = client.post(
        "/auth/code/verify",
        data={
            "csrf_token": csrf_from(second),
            "email": "resend@example.com",
            "code": first_code,
            "next": "/app",
        },
    )
    assert old_result.status_code == 400
    assert "invalid or expired" in old_result.text


def test_external_next_url_is_not_accepted(client):
    requested = request_code(client, "redirect@example.com", "https://attacker.example/phish")
    response = client.post(
        "/auth/code/verify",
        data={
            "csrf_token": csrf_from(requested),
            "email": "redirect@example.com",
            "code": demo_code_from(requested),
            "next": "https://attacker.example/phish",
        },
        follow_redirects=False,
    )
    assert response.headers["location"] == "/app"


def test_dashboard_closing_soon_is_ordered_by_deadline(client):
    login = client.get("/login")
    client.post("/demo", data={"csrf_token": csrf_from(login)})
    page = BeautifulSoup(client.get("/app").text, "html.parser")
    titles = [item.get_text(strip=True) for item in page.select(".timeline strong")]
    assert titles[:2] == [
        "Brick bungalow · renovation scenario",
        "Two-flat · forfeiture sale scenario",
    ]
