import os

os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": "sqlite:////tmp/dealsig_pytest.db",
        "SESSION_SECRET": "test-session-secret-that-is-more-than-thirty-two-characters",
        "DEMO_MODE": "true",
        "BILLING_BYPASS": "true",
        "SEED_DEMO_DATA": "true",
        "ALLOWED_HOSTS": "testserver,localhost,127.0.0.1",
        "RESEND_API_KEY": "",
        "PASSKEY_RP_ID": "testserver",
        "PASSKEY_ORIGIN": "http://testserver",
    }
)

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
