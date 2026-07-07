"""Shared pytest fixtures.

Module 1 provides the FastAPI test client against the app factory. Database
and factory fixtures are expanded as later modules add models and routers.
"""

from __future__ import annotations

import os

# Ensure required settings exist before importing the app under test.
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-use-only")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://revos:revos@localhost:5432/revos_test")
# Hermetic rate limiting — no Redis dependency in tests.
os.environ.setdefault("RATE_LIMIT_STORAGE_URI", "memory://")
# Isolated media storage so tests never write into the repo.
import tempfile  # noqa: E402

os.environ.setdefault("STORAGE_LOCAL_DIR", tempfile.mkdtemp(prefix="revos-media-test-"))

import pytest
import pytest_asyncio
from app.core.rate_limit import reset_limits
from app.core.rate_limit import state as rl_state
from app.database import get_session
from app.main import create_app
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _disable_rate_limit():
    """Disable IP rate limiting by default; the rate-limit test opts back in."""
    rl_state.enabled = False
    reset_limits()
    yield
    rl_state.enabled = True
    reset_limits()


@pytest_asyncio.fixture
async def async_session_factory():
    """Async in-memory SQLite (aiosqlite) with the full schema."""
    import app.models  # noqa: F401 — register tables on metadata

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    # autoflush=False to match production (app/database.py) — a query-before-flush
    # ordering bug (e.g. adding a row then immediately querying for it) would
    # otherwise be masked here by SQLAlchemy's default autoflush and slip
    # through tests that pass against the real deployment's session config.
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def api(app, async_session_factory):
    """httpx client wired to the app with an overridden async DB session."""

    async def _override_session():
        async with async_session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.pop(get_session, None)


@pytest_asyncio.fixture
async def make_client(app, async_session_factory):
    """Factory that mints fresh AsyncClient instances sharing the same DB.

    Each client has its own cookie jar, so multi-user tests avoid the CSRF
    double-submit collision that occurs when two users share one client.
    """

    async def _override_session():
        async with async_session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_session] = _override_session
    transport = ASGITransport(app=app)
    clients: list[AsyncClient] = []

    async def _make() -> AsyncClient:
        client = AsyncClient(transport=transport, base_url="http://testserver")
        await client.__aenter__()
        clients.append(client)
        return client

    yield _make

    for c in clients:
        try:
            await c.__aexit__(None, None, None)
        except Exception:
            pass
    app.dependency_overrides.pop(get_session, None)


@pytest_asyncio.fixture
async def owner_credentials(async_session_factory):
    """Seed an owner user and return its login credentials."""
    from app.models.user import Role
    from app.services.auth_service import create_user

    creds = {"email": "owner@test.com", "password": "OwnerPass123"}
    async with async_session_factory() as session:
        await create_user(
            session, email=creds["email"], password=creds["password"],
            full_name="Test Owner", role=Role.owner,
        )
        await session.commit()
    return creds


@pytest_asyncio.fixture
async def make_user(async_session_factory):
    """Factory: create a user with a given role. Returns its credentials dict."""
    from app.services.auth_service import create_user

    async def _make(email: str, password: str, role):
        from app.models.base import utcnow

        async with async_session_factory() as session:
            user = await create_user(session, email=email, password=password,
                             full_name=email, role=role)
            # This fixture represents an already-onboarded team member, not a
            # fresh signup going through the real registration flow — verify
            # so tests exercising role/permission logic don't also have to
            # deal with the (unrelated) email-verification gate.
            user.email_verified_at = utcnow()
            session.add(user)
            await session.commit()
        return {"email": email, "password": password}

    return _make


@pytest.fixture
def db_session():
    """In-memory SQLite session with the full schema for fast model tests."""
    import app.models  # noqa: F401 — register tables on metadata

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)
