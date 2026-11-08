"""Organization, hospital, department and audit behaviour tests."""
from __future__ import annotations

from tests.conftest import auth


def test_central_can_create_governorate_and_hospital(client, tokens):
    h = auth(tokens["central"])
    r = client.post("/api/v1/organizations", headers=h,
                    json={"name_ar": "محافظة حضرموت (اختبار)", "level": "governorate", "code": "GOV-HADRAMOUT-T"})
    assert r.status_code == 201, r.text
    gov_id = r.json()["id"]

    r2 = client.post("/api/v1/hospitals", headers=h,
                     json={"name_ar": "مستشفى اختبار حضرموت", "code": "H-HADRAMOUT-T", "governorate_id": gov_id})
    assert r2.status_code == 201, r2.text
    assert r2.json()["code"] == "H-HADRAMOUT-T"


def test_duplicate_hospital_code_conflict(client, tokens):
    h = auth(tokens["central"])
    r = client.post("/api/v1/hospitals", headers=h,
                    json={"name_ar": "مكرر", "code": "H-SANAA-REP"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "conflict"


def test_hospital_manager_can_add_department_to_own_hospital(client, tokens):
    from app.db.seed_demo import HOSP_REPUBLICAN_ID

    r = client.post(
        f"/api/v1/hospitals/{HOSP_REPUBLICAN_ID}/departments",
        headers=auth(tokens["rep_manager"]),
        json={"name_ar": "المختبر", "hospital_id": str(HOSP_REPUBLICAN_ID), "code": "LAB"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["name_ar"] == "المختبر"


def test_quality_manager_cannot_add_department(client, tokens):
    from app.db.seed_demo import HOSP_REPUBLICAN_ID

    r = client.post(
        f"/api/v1/hospitals/{HOSP_REPUBLICAN_ID}/departments",
        headers=auth(tokens["rep_quality"]),
        json={"name_ar": "قسم غير مصرح", "hospital_id": str(HOSP_REPUBLICAN_ID), "code": "X"},
    )
    assert r.status_code == 403


def test_audit_log_records_actions(client, tokens):
    h = auth(tokens["central"])
    client.post("/api/v1/organizations", headers=h,
                json={"name_ar": "محافظة أرشفة (اختبار)", "level": "governorate", "code": "GOV-AUDIT-T"})
    r = client.get("/api/v1/audit-log?entity_type=organization", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(e["action"] == "create" for e in body["entries"])


def test_read_only_cannot_view_audit(client, tokens):
    r = client.get("/api/v1/audit-log", headers=auth(tokens["rep_reader"]))
    assert r.status_code == 403


def test_user_creation_and_assignment(client, tokens):
    h = auth(tokens["central"])
    r = client.post("/api/v1/users", headers=h,
                    json={"username": "test.officer", "display_name": "مسؤول اختبار",
                          "password": "TestPass@123"})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]

    r2 = client.post("/api/v1/users/assignments", headers=h,
                     json={"user_id": uid, "role_code": "indicator_officer",
                           "scope_type": "central"})
    assert r2.status_code == 201, r2.text

    # The new user can log in and sees the assigned role.
    r3 = client.post("/api/v1/auth/login", json={"username": "test.officer", "password": "TestPass@123"})
    assert r3.status_code == 200
    tok = r3.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers=auth(tok))
    assert "indicator_officer" in me.json()["roles"]


def test_weak_password_rejected(client, tokens):
    r = client.post("/api/v1/users", headers=auth(tokens["central"]),
                    json={"username": "weak.one", "display_name": "ضعيف", "password": "123"})
    assert r.status_code == 422
