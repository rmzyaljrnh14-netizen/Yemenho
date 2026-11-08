"""Authentication and permission tests."""
from __future__ import annotations

from tests.conftest import DEMO_PASSWORD, auth, login


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_login_success(client):
    r = client.post("/api/v1/auth/login", json={"username": "central.admin", "password": DEMO_PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_in"] > 0


def test_login_wrong_password(client):
    r = client.post("/api/v1/auth/login", json={"username": "central.admin", "password": "wrong-password"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "unauthenticated"


def test_login_unknown_user(client):
    r = client.post("/api/v1/auth/login", json={"username": "nobody.here", "password": "whatever123"})
    assert r.status_code == 401


def test_me_returns_roles_and_scopes(client, tokens):
    r = client.get("/api/v1/auth/me", headers=auth(tokens["rep_quality"]))
    assert r.status_code == 200
    body = r.json()
    assert "quality_manager" in body["roles"]
    assert "indicator.enter" in body["scopes"]
    assert body["scope_org"]["level"] == "hospital"


def test_me_requires_auth(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_rejects_garbage_token(client):
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "token_expired"


def test_refresh_flow(client):
    r = client.post("/api/v1/auth/login", json={"username": "rep.reader", "password": DEMO_PASSWORD})
    refresh = r.json()["refresh_token"]
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 200
    assert r2.json()["access_token"]


def test_read_only_cannot_manage_users(client, tokens):
    r = client.get("/api/v1/users", headers=auth(tokens["rep_reader"]))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "forbidden"


def test_quality_manager_cannot_manage_orgs(client, tokens):
    r = client.post(
        "/api/v1/organizations",
        headers=auth(tokens["rep_quality"]),
        json={"name_ar": "جهة تجريبية", "level": "governorate"},
    )
    assert r.status_code == 403


def test_logout(client, tokens):
    r = client.post("/api/v1/auth/logout", headers=auth(tokens["rep_reader"]))
    assert r.status_code == 200
    assert r.json()["ok"] is True
