"""Audit-log API behaviour (v0.11).

Covers the three properties an audit log must have: it is *readable* by the
people allowed to see it, *isolated* so a hospital never reads another
hospital's entries, and *immutable* so nothing can change or erase a record.
"""
from __future__ import annotations

import uuid

from tests.conftest import auth

from app.db.seed_demo import HOSP_ALJUMHOURI_ID, HOSP_REPUBLICAN_ID


def _create_org(client, token, code: str) -> str:
    r = client.post(
        "/api/v1/organizations",
        headers=auth(token),
        json={"name_ar": f"جهة {code}", "level": "governorate", "code": code},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_audit_page_shape_and_labels(client, tokens):
    _create_org(client, tokens["central"], "GOV-AUDIT-SHAPE")
    r = client.get("/api/v1/audit-log?limit=5", headers=auth(tokens["central"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"total", "limit", "offset", "entries"} <= set(body)
    assert body["limit"] == 5
    assert len(body["entries"]) <= 5
    entry = body["entries"][0]
    # Readable Arabic summary and labels, not raw codes.
    assert entry["summary_ar"]
    assert entry["entity_label_ar"]
    assert entry["action_label_ar"]


def test_audit_filters_by_entity_type(client, tokens):
    _create_org(client, tokens["central"], "GOV-AUDIT-FILTER")
    r = client.get("/api/v1/audit-log?entity_type=organization", headers=auth(tokens["central"]))
    assert r.status_code == 200
    assert all(e["entity_type"] == "organization" for e in r.json()["entries"])


def test_audit_facets_list_entity_types(client, tokens):
    _create_org(client, tokens["central"], "GOV-AUDIT-FACET")
    r = client.get("/api/v1/audit-log/facets", headers=auth(tokens["central"]))
    assert r.status_code == 200, r.text
    body = r.json()
    codes = {item["code"] for item in body["entity_types"]}
    assert "organization" in codes
    assert all("label_ar" in item and "count" in item for item in body["entity_types"])


def test_hospital_user_only_sees_own_hospital_entries(client, tokens):
    """A quality manager at one hospital never reads the other hospital's log."""
    # Produce an auditable action at each hospital (a risk entry).
    for token, label in [(tokens["rep_quality"], "خطر أرشفة أ"), (tokens["jum_quality"], "خطر أرشفة ب")]:
        r = client.post(
            "/api/v1/quality/risks",
            headers=auth(token),
            json={"title": label, "category": "clinical"},
        )
        assert r.status_code == 201, r.text

    r = client.get("/api/v1/audit-log?entity_type=risk", headers=auth(tokens["rep_quality"]))
    assert r.status_code == 200, r.text
    hospitals = {e["hospital_id"] for e in r.json()["entries"]}
    assert hospitals <= {str(HOSP_REPUBLICAN_ID)}
    assert str(HOSP_ALJUMHOURI_ID) not in hospitals


def test_hospital_user_cannot_filter_another_hospital(client, tokens):
    r = client.get(
        f"/api/v1/audit-log?hospital_id={HOSP_ALJUMHOURI_ID}",
        headers=auth(tokens["rep_quality"]),
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "forbidden"


def test_read_only_user_forbidden(client, tokens):
    r = client.get("/api/v1/audit-log", headers=auth(tokens["rep_reader"]))
    assert r.status_code == 403


def test_unauthenticated_forbidden(client):
    r = client.get("/api/v1/audit-log")
    assert r.status_code == 401


def test_audit_log_is_read_only(client, tokens):
    """There is deliberately no way to write, edit or delete through the API."""
    h = auth(tokens["central"])
    assert client.post("/api/v1/audit-log", headers=h, json={}).status_code in (404, 405)
    assert client.put("/api/v1/audit-log", headers=h, json={}).status_code in (404, 405)
    assert client.delete("/api/v1/audit-log", headers=h).status_code in (404, 405)


def test_audit_log_cannot_be_edited_in_the_database(client, tokens):
    """Even a direct UPDATE is refused by row-level security for the app role."""
    from sqlalchemy import text

    from app.db.base import SessionLocal

    db = SessionLocal()
    try:
        row = db.execute(text("SELECT id FROM audit_log LIMIT 1")).fetchone()
        if row is None:
            return
        db.rollback()
        # As the app role, an UPDATE matches no policy and so changes nothing.
        result = db.execute(
            text("UPDATE audit_log SET action = 'tampered' WHERE id = :id RETURNING id"),
            {"id": row[0]},
        ).fetchall()
        db.rollback()
        assert result == []
    finally:
        db.close()


def test_audit_csv_export_has_header(client, tokens):
    _create_org(client, tokens["central"], "GOV-AUDIT-CSV")
    r = client.get("/api/v1/audit-log/export.csv", headers=auth(tokens["central"]))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    text_body = r.content.decode("utf-8")
    assert "الوقت" in text_body
    assert "الإجراء" in text_body


def test_audit_csv_export_respects_scope(client, tokens):
    r = client.get("/api/v1/audit-log/export.csv", headers=auth(tokens["rep_quality"]))
    assert r.status_code == 200
    # No other hospital's name should appear in a hospital user's export.
    assert "الجمهوري الآخر" not in r.content.decode("utf-8")


def test_audit_xlsx_export_ok(client, tokens):
    _create_org(client, tokens["central"], "GOV-AUDIT-XLSX")
    r = client.get("/api/v1/audit-log/export.xlsx", headers=auth(tokens["central"]))
    assert r.status_code == 200, r.text
    assert r.content[:2] == b"PK"  # zip container: a real xlsx


def test_audit_pagination_offset(client, tokens):
    for i in range(3):
        _create_org(client, tokens["central"], f"GOV-AUDIT-PAGE-{i}")
    h = auth(tokens["central"])
    first = client.get("/api/v1/audit-log?entity_type=organization&limit=1&offset=0", headers=h).json()
    second = client.get("/api/v1/audit-log?entity_type=organization&limit=1&offset=1", headers=h).json()
    assert first["entries"][0]["id"] != second["entries"][0]["id"]
    assert first["total"] == second["total"]


def test_audit_login_events_visible_to_central_only(client, tokens):
    r = client.get("/api/v1/audit-log?entity_type=auth", headers=auth(tokens["central"]))
    assert r.status_code == 200
    assert r.json()["total"] >= 1
    # A hospital user cannot see global auth events (they carry no hospital).
    r2 = client.get("/api/v1/audit-log?entity_type=auth", headers=auth(tokens["rep_quality"]))
    assert r2.status_code == 200
    assert r2.json()["total"] == 0
