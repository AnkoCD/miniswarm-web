import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+pysqlite://"
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-tests"

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import hash_password
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import User, UserRole


@pytest.fixture(autouse=True)
def clean_database():
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.add(
            User(
                username="admin",
                password_hash=hash_password("very-secure-test-password"),
                role=UserRole.ADMIN,
            )
        )
        db.commit()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as value:
        yield value


@pytest.fixture
def authenticated_client(client, monkeypatch):
    monkeypatch.setattr("app.api.tasks.run_task.apply_async", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "app.api.tasks.analyze_archive_memory_task.apply_async",
        lambda *args, **kwargs: None,
    )
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "very-secure-test-password"},
    )
    assert response.status_code == 200
    return client
