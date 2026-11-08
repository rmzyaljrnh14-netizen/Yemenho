"""Test fixtures. Uses a dedicated database (yhq_test) so real/dev data is untouched."""
from __future__ import annotations

import os
import uuid

# Must be set before app modules are imported (engine + settings are cached).
TEST_DB = "yhq_test"
TEST_DB_URL = os.environ.get(
    "YHQ_TEST_DATABASE_URL",
    f"postgresql+psycopg://yhq_app:yhq_app_dev_pw@127.0.0.1:5432/{TEST_DB}",
)
TEST_ADMIN_URL = os.environ.get(
    "YHQ_TEST_ADMIN_DATABASE_URL",
    f"postgresql+psycopg://yhq:yhq_dev_pw@127.0.0.1:5432/{TEST_DB}",
)
os.environ["YHQ_DATABASE_URL"] = TEST_DB_URL
os.environ["YHQ_ADMIN_DATABASE_URL"] = TEST_ADMIN_URL
os.environ["YHQ_JWT_SECRET"] = "test-secret-not-a-real-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.base import AdminSessionLocal, engine  # noqa: E402
from app.db.migrate import run_migrations  # noqa: E402
from app.db.seed_demo import DEMO_PASSWORD, seed  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _prepare_db():
    # Create the database if it does not exist (connect to the admin db).
    from sqlalchemy import create_engine

    admin_url = TEST_ADMIN_URL.rsplit("/", 1)[0] + "/postgres"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()

    # Migrations create the app role + grants and run all schema changes.
    run_migrations()
    db = AdminSessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    yield
    engine.dispose()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def login(client: TestClient, username: str, password: str = DEMO_PASSWORD) -> str:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def tokens(client) -> dict:
    return {
        "central": login(client, "central.admin"),
        "gov": login(client, "sanaa.gov"),
        "rep_manager": login(client, "rep.manager"),
        "rep_quality": login(client, "rep.quality"),
        "rep_reader": login(client, "rep.reader"),
        "jum_quality": login(client, "jum.quality"),
    }
