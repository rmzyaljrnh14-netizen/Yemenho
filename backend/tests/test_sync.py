"""Tests for the offline sync engine (v0.6) — protocol docs/14.

Covers: idempotency (S5), stale-revision conflict (S6), approved-period
protection (S7), cursor-based pull, bootstrap, authorization/isolation, and the
offline-first flow (create period+value on the node, push, see it on the server).
"""
from __future__ import annotations

import uuid

from app.db.seed_demo import HOSP_ALJUMHOURI_ID, HOSP_REPUBLICAN_ID

from .conftest import auth

SYNC = "/api/v1/sync"
PERIODS = "/api/v1/periods"
YEAR = 2023  # a year no other test writes to


def _node(name: str = "node") -> str:
    return f"node-{name}-{uuid.uuid4()}"


def _indicator_id(client, token, code: str) -> str:
    rows = client.get("/api/v1/indicators", headers=auth(token)).json()
    return next(i["id"] for i in rows if i["code"] == code)


def _push(client, token, node_id, operations, hospital_id=HOSP_REPUBLICAN_ID):
    r = client.post(
        f"{SYNC}/push",
        headers=auth(token),
        json={
            "node_id": node_id,
            "hospital_id": str(hospital_id),
            "batch_id": f"batch-{uuid.uuid4()}",
            "operations": operations,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


# ---- Access control ----
def test_sync_requires_auth(client):
    assert client.get(f"{SYNC}/status").status_code == 401
    assert client.post(f"{SYNC}/push", json={"node_id": "n", "batch_id": "b", "operations": []}).status_code == 401


def test_read_only_user_cannot_push(client, tokens):
    node = _node()
    r = client.post(
        f"{SYNC}/push",
        headers=auth(tokens["rep_reader"]),
        json={"node_id": node, "hospital_id": str(HOSP_REPUBLICAN_ID), "batch_id": "b1", "operations": []},
    )
    assert r.status_code == 403


def test_node_cannot_sync_another_hospital(client, tokens):
    # A Republican-hospital user cannot push for the other hospital.
    node = _node()
    r = client.post(
        f"{SYNC}/push",
        headers=auth(tokens["rep_quality"]),
        json={"node_id": node, "hospital_id": str(HOSP_ALJUMHOURI_ID), "batch_id": "b", "operations": []},
    )
    assert r.status_code == 403


# ---- Offline-first create, then push (S1/S2/S3) ----
def test_offline_create_period_and_value_then_push(client, tokens):
    token = tokens["rep_quality"]
    node = _node("create")
    period_id = str(uuid.uuid4())
    value_id = str(uuid.uuid4())
    indicator_id = _indicator_id(client, token, "AUDIT-COVER")

    # Two operations produced while offline: create a period, then a value in it.
    out = _push(
        client, token, node,
        [
            {"op_id": f"op-{uuid.uuid4()}", "entity_type": "reporting_period", "entity_id": period_id,
             "op": "upsert", "base_rev": 0,
             "payload": {"period_type": "monthly", "year": YEAR, "month": 1}},
            {"op_id": f"op-{uuid.uuid4()}", "entity_type": "indicator_value", "entity_id": value_id,
             "op": "upsert", "base_rev": 0,
             "payload": {"period_id": period_id, "indicator_id": indicator_id, "numerator": 18, "denominator": 20}},
        ],
    )
    assert [r["status"] for r in out["results"]] == ["applied", "applied"]

    # The value is now visible on the server, computed server-side (18/20*100 = 90).
    detail = client.get(f"{PERIODS}/{period_id}", headers=auth(token)).json()
    assert len(detail["values"]) == 1
    assert float(detail["values"][0]["value"]) == 90.0


# ---- Idempotency (S5) ----
def test_resending_same_batch_does_not_duplicate(client, tokens):
    token = tokens["rep_quality"]
    node = _node("idem")
    period_id = str(uuid.uuid4())
    op_id = f"op-{uuid.uuid4()}"
    op = {
        "op_id": op_id, "entity_type": "reporting_period", "entity_id": period_id,
        "op": "upsert", "base_rev": 0,
        "payload": {"period_type": "monthly", "year": YEAR, "month": 2},
    }
    first = _push(client, token, node, [op])
    second = _push(client, token, node, [op])
    assert first["results"][0]["status"] == "applied"
    # Same op_id -> same stored result, no second write.
    assert second["results"][0]["status"] == "applied"
    assert second["results"][0]["new_rev"] == first["results"][0]["new_rev"]

    seq = client.get(f"{SYNC}/pull", params={"since": 0, "limit": 1000}, headers=auth(token)).json()
    matching = [c for c in seq["changes"] if c["entity_id"] == period_id]
    assert len(matching) == 1  # exactly one change recorded, not two


# ---- Conflict on stale revision (S6) ----
def test_stale_base_rev_is_a_conflict_not_an_overwrite(client, tokens):
    token = tokens["rep_quality"]
    node = _node("conflict")
    period_id = str(uuid.uuid4())
    value_id = str(uuid.uuid4())
    indicator_id = _indicator_id(client, token, "AUDIT-COVER")

    _push(client, token, node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "reporting_period", "entity_id": period_id,
         "op": "upsert", "base_rev": 0, "payload": {"period_type": "monthly", "year": YEAR, "month": 3}},
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "indicator_value", "entity_id": value_id,
         "op": "upsert", "base_rev": 0,
         "payload": {"period_id": period_id, "indicator_id": indicator_id, "numerator": 10, "denominator": 20}},
    ])
    # A second, well-behaved node updates the value to rev 2.
    ok = _push(client, token, _node("other"), [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "indicator_value", "entity_id": value_id,
         "op": "upsert", "base_rev": 1,
         "payload": {"period_id": period_id, "indicator_id": indicator_id, "numerator": 15, "denominator": 20}},
    ])
    assert ok["results"][0]["status"] == "applied"
    assert ok["results"][0]["new_rev"] == 2

    # The first node re-sends against its stale base_rev=1.
    stale = _push(client, token, node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "indicator_value", "entity_id": value_id,
         "op": "upsert", "base_rev": 1,
         "payload": {"period_id": period_id, "indicator_id": indicator_id, "numerator": 99, "denominator": 100}},
    ])
    result = stale["results"][0]
    assert result["status"] == "conflict"
    assert result["current_rev"] == 2
    assert result["server_payload"]["numerator"] == 15.0  # server copy wins

    detail = client.get(f"{PERIODS}/{period_id}", headers=auth(token)).json()
    assert float(detail["values"][0]["numerator"]) == 15.0  # not overwritten with 99


# ---- Approved period is frozen (S7) ----
def test_approved_period_rejects_offline_edit(client, tokens):
    token = tokens["rep_quality"]
    node = _node("approved")
    period_id = str(uuid.uuid4())
    value_id = str(uuid.uuid4())
    indicator_id = _indicator_id(client, token, "AUDIT-COVER")

    _push(client, token, node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "reporting_period", "entity_id": period_id,
         "op": "upsert", "base_rev": 0, "payload": {"period_type": "monthly", "year": YEAR, "month": 4}},
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "indicator_value", "entity_id": value_id,
         "op": "upsert", "base_rev": 0,
         "payload": {"period_id": period_id, "indicator_id": indicator_id, "numerator": 18, "denominator": 20}},
    ])
    # Approve it via the online workflow (submit as quality, approve as manager).
    r = client.post(f"{PERIODS}/{period_id}/submit", headers=auth(token), json={})
    assert r.status_code == 200, r.text
    r = client.post(f"{PERIODS}/{period_id}/approve", headers=auth(tokens["rep_manager"]), json={})
    assert r.status_code == 200, r.text

    # A node tries to change the value: rejected, approved data stands.
    out = _push(client, token, node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "indicator_value", "entity_id": value_id,
         "op": "upsert", "base_rev": 1,
         "payload": {"period_id": period_id, "indicator_id": indicator_id, "numerator": 5, "denominator": 20}},
    ])
    assert out["results"][0]["status"] == "rejected"
    assert out["results"][0]["reason"] == "already_approved"


# ---- Zero denominator (S14) ----
def test_zero_denominator_is_stored_as_empty_not_crash(client, tokens):
    token = tokens["rep_quality"]
    node = _node("zero")
    period_id = str(uuid.uuid4())
    value_id = str(uuid.uuid4())
    indicator_id = _indicator_id(client, token, "AUDIT-COVER")

    _push(client, token, node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "reporting_period", "entity_id": period_id,
         "op": "upsert", "base_rev": 0, "payload": {"period_type": "monthly", "year": YEAR, "month": 5}},
    ])
    out = _push(client, token, node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "indicator_value", "entity_id": value_id,
         "op": "upsert", "base_rev": 0,
         "payload": {"period_id": period_id, "indicator_id": indicator_id, "numerator": 3, "denominator": 0}},
    ])
    assert out["results"][0]["status"] == "applied"
    detail = client.get(f"{PERIODS}/{period_id}", headers=auth(token)).json()
    assert detail["values"][0]["value"] is None


# ---- Server-authoritative entities are refused ----
def test_indicator_is_not_pushable(client, tokens):
    node = _node("indicator")
    out = _push(client, tokens["rep_quality"], node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "indicator", "entity_id": str(uuid.uuid4()),
         "op": "upsert", "base_rev": 0, "payload": {"name_ar": "مؤشر مزيف"}},
    ])
    assert out["results"][0]["status"] == "rejected"
    assert out["results"][0]["reason"] == "unsupported_entity"


# ---- Cursor pull ----
def test_pull_returns_changes_after_cursor(client, tokens):
    token = tokens["rep_quality"]
    node = _node("pull")
    period_id = str(uuid.uuid4())
    _push(client, token, node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "reporting_period", "entity_id": period_id,
         "op": "upsert", "base_rev": 0, "payload": {"period_type": "monthly", "year": YEAR, "month": 7}},
    ])
    first = client.get(f"{SYNC}/pull", params={"since": 0, "limit": 1000}, headers=auth(token)).json()
    assert any(c["entity_id"] == period_id for c in first["changes"])
    assert first["to_seq"] >= 1

    # Pulling again from the cursor returns nothing new (idempotent read).
    again = client.get(f"{SYNC}/pull", params={"since": first["to_seq"], "limit": 1000}, headers=auth(token)).json()
    assert again["changes"] == []
    assert again["to_seq"] == first["to_seq"]


# ---- Bootstrap ----
def test_bootstrap_returns_library_and_hospital_scoped_data(client, tokens):
    node = _node("bootstrap")
    out = client.post(
        f"{SYNC}/bootstrap",
        params={"node_id": node, "hospital_id": str(HOSP_REPUBLICAN_ID)},
        headers=auth(tokens["rep_quality"]),
    ).json()
    assert len(out["indicators"]) >= 20
    # The library is national (no hospital), assignments/periods are this hospital's.
    assert all(a["hospital_id"] == str(HOSP_REPUBLICAN_ID) for a in out["assignments"])


# ---- Status ----
def test_status_reports_pending_after_push(client, tokens):
    token = tokens["rep_quality"]
    node = _node("status")
    _push(client, token, node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "reporting_period", "entity_id": str(uuid.uuid4()),
         "op": "upsert", "base_rev": 0, "payload": {"period_type": "monthly", "year": YEAR, "month": 8}},
    ])
    st = client.get(f"{SYNC}/status", params={"node_id": node}, headers=auth(token)).json()
    assert st["node_id"] == node
    assert st["server_seq"] >= 1


# ---- Incidents (v0.7): the patient-safety flow must work offline ----
def _incident_payload(**over) -> dict:
    base = {
        "title": "حادث تجريبي من جهاز دون اتصال",
        "description": "سقوط مريض أثناء النقل.",
        "incident_type": "fall",
        "severity": "moderate",
        "patient_harm": "mild",
        "immediate_action": "أُسعف المريض فوراً.",
    }
    base.update(over)
    return base


def test_incident_created_offline_is_applied_with_server_code(client, tokens):
    token = tokens["rep_quality"]
    node = _node("incident-new")
    incident_id = str(uuid.uuid4())
    out = _push(client, token, node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "incident", "entity_id": incident_id,
         "op": "upsert", "base_rev": 0, "payload": _incident_payload()},
    ])
    assert out["results"][0]["status"] == "applied"
    assert out["results"][0]["new_rev"] == 1

    got = client.get(f"/api/v1/quality/incidents/{incident_id}", headers=auth(token)).json()
    assert got["code"].startswith("INC-")
    assert got["status"] == "reported"  # the node never sets the workflow status
    assert got["severity"] == "moderate"


def test_incident_push_is_idempotent(client, tokens):
    token = tokens["rep_quality"]
    node = _node("incident-idem")
    incident_id = str(uuid.uuid4())
    op = {"op_id": f"op-{uuid.uuid4()}", "entity_type": "incident", "entity_id": incident_id,
          "op": "upsert", "base_rev": 0, "payload": _incident_payload(title="حادث مكرر الإرسال")}
    first = _push(client, token, node, [op])
    second = _push(client, token, node, [op])
    assert first["results"][0]["status"] == "applied"
    # The same op_id is never applied twice: the stored result is returned.
    assert second["results"][0]["status"] == "applied"
    rows = client.get("/api/v1/quality/incidents", headers=auth(token)).json()
    assert sum(1 for r in rows if r["id"] == incident_id) == 1


def test_incident_stale_revision_conflicts_not_overwrites(client, tokens):
    token = tokens["rep_quality"]
    node = _node("incident-conflict")
    incident_id = str(uuid.uuid4())
    _push(client, token, node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "incident", "entity_id": incident_id,
         "op": "upsert", "base_rev": 0, "payload": _incident_payload(title="النسخة الأولى")},
    ])
    # A second edit that still believes the row is at rev 0 is stale.
    out = _push(client, token, node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "incident", "entity_id": incident_id,
         "op": "upsert", "base_rev": 0, "payload": _incident_payload(title="تعديل قديم")},
    ])
    assert out["results"][0]["status"] == "conflict"
    got = client.get(f"/api/v1/quality/incidents/{incident_id}", headers=auth(token)).json()
    assert got["title"] == "النسخة الأولى"  # the server version won


def test_incident_rejects_bad_vocabulary(client, tokens):
    node = _node("incident-bad")
    out = _push(client, tokens["rep_quality"], node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "incident", "entity_id": str(uuid.uuid4()),
         "op": "upsert", "base_rev": 0, "payload": _incident_payload(severity="catastrophic_typo")},
    ])
    assert out["results"][0]["status"] == "rejected"
    assert out["results"][0]["reason"] == "validation_failed"


def test_bootstrap_includes_incidents(client, tokens):
    node = _node("bootstrap-inc")
    out = client.post(
        f"{SYNC}/bootstrap",
        params={"node_id": node, "hospital_id": str(HOSP_REPUBLICAN_ID)},
        headers=auth(tokens["rep_quality"]),
    ).json()
    assert "incidents" in out
    assert all(i["hospital_id"] == str(HOSP_REPUBLICAN_ID) for i in out["incidents"])
