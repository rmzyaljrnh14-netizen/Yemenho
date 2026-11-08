"""Offline sync for the remaining quality modules (v0.14) — CAPA and risks.

A hospital must be able to plan a corrective/preventive action and add a risk to
the register with no internet. Both join the sync protocol in docs/14 exactly as
incidents do: unique op_id idempotency, a revision counter so a stale push is a
conflict (never a silent overwrite), server-owned codes and sign-off, and full
hospital isolation.
"""
from __future__ import annotations

import uuid

from app.db.seed_demo import HOSP_ALJUMHOURI_ID, HOSP_REPUBLICAN_ID

from .conftest import auth

SYNC = "/api/v1/sync"
CAPA = "/api/v1/quality/capa"
RISKS = "/api/v1/quality/risks"


def _node(name: str = "node") -> str:
    return f"node-{name}-{uuid.uuid4()}"


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


def _capa_payload(**over) -> dict:
    base = {
        "kind": "corrective",
        "title": "إجراء تصحيحي من جهاز دون اتصال",
        "description_ar": "تدريب الكادر على التحقق من هوية المريض.",
        "owner_name_ar": "مسؤول الجودة",
        "due_date": "2026-06-30",
        "priority": "high",
        "status": "open",
    }
    base.update(over)
    return base


def _risk_payload(**over) -> dict:
    base = {
        "title": "خطر تجريبي من جهاز دون اتصال",
        "description_ar": "احتمال تعطل جهاز المراقبة.",
        "category": "equipment",
        "likelihood": 4,
        "impact": 5,
        "mitigation_ar": "صيانة دورية.",
        "owner_name_ar": "مسؤول الصيانة",
        "review_date": "2026-07-15",
        "status": "open",
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# CAPA
# ---------------------------------------------------------------------------
def test_capa_created_offline_is_applied(client, tokens):
    token = tokens["rep_quality"]
    node = _node("capa-new")
    capa_id = str(uuid.uuid4())
    out = _push(client, token, node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "capa_action", "entity_id": capa_id,
         "op": "upsert", "base_rev": 0, "payload": _capa_payload()},
    ])
    assert out["results"][0]["status"] == "applied"
    assert out["results"][0]["new_rev"] == 1

    rows = client.get(CAPA, headers=auth(token)).json()
    row = next(r for r in rows if r["id"] == capa_id)
    assert row["title"] == "إجراء تصحيحي من جهاز دون اتصال"
    assert row["priority"] == "high"
    assert row["status"] == "open"
    assert row["due_date"] == "2026-06-30"


def test_capa_push_is_idempotent(client, tokens):
    token = tokens["rep_quality"]
    node = _node("capa-idem")
    capa_id = str(uuid.uuid4())
    op = {"op_id": f"op-{uuid.uuid4()}", "entity_type": "capa_action", "entity_id": capa_id,
          "op": "upsert", "base_rev": 0, "payload": _capa_payload(title="إجراء مكرر الإرسال")}
    _push(client, token, node, [op])
    _push(client, token, node, [op])  # same op_id replayed
    rows = client.get(CAPA, headers=auth(token)).json()
    assert sum(1 for r in rows if r["id"] == capa_id) == 1


def test_capa_stale_revision_conflicts_not_overwrites(client, tokens):
    token = tokens["rep_quality"]
    node = _node("capa-conflict")
    capa_id = str(uuid.uuid4())
    _push(client, token, node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "capa_action", "entity_id": capa_id,
         "op": "upsert", "base_rev": 0, "payload": _capa_payload(title="النسخة الأولى")},
    ])
    out = _push(client, token, node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "capa_action", "entity_id": capa_id,
         "op": "upsert", "base_rev": 0, "payload": _capa_payload(title="تعديل قديم")},
    ])
    assert out["results"][0]["status"] == "conflict"
    rows = client.get(CAPA, headers=auth(token)).json()
    row = next(r for r in rows if r["id"] == capa_id)
    assert row["title"] == "النسخة الأولى"


def test_capa_node_cannot_self_sign_off(client, tokens):
    """A device may only report open/in_progress; done/verified stay server-side."""
    token = tokens["rep_quality"]
    node = _node("capa-signoff")
    capa_id = str(uuid.uuid4())
    out = _push(client, token, node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "capa_action", "entity_id": capa_id,
         "op": "upsert", "base_rev": 0, "payload": _capa_payload(status="verified")},
    ])
    assert out["results"][0]["status"] == "rejected"
    assert out["results"][0]["reason"] == "validation_failed"


def test_capa_rejects_bad_priority(client, tokens):
    node = _node("capa-bad")
    out = _push(client, tokens["rep_quality"], node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "capa_action", "entity_id": str(uuid.uuid4()),
         "op": "upsert", "base_rev": 0, "payload": _capa_payload(priority="urgent")},
    ])
    assert out["results"][0]["status"] == "rejected"
    assert out["results"][0]["reason"] == "validation_failed"


# ---------------------------------------------------------------------------
# Risks
# ---------------------------------------------------------------------------
def test_risk_created_offline_scores_on_server(client, tokens):
    token = tokens["rep_quality"]
    node = _node("risk-new")
    risk_id = str(uuid.uuid4())
    out = _push(client, token, node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "risk", "entity_id": risk_id,
         "op": "upsert", "base_rev": 0, "payload": _risk_payload(likelihood=4, impact=5)},
    ])
    assert out["results"][0]["status"] == "applied"

    rows = client.get(RISKS, headers=auth(token)).json()
    row = next(r for r in rows if r["id"] == risk_id)
    assert row["code"].startswith("RSK-")  # the server assigns the code
    assert row["score"] == 20  # computed column: likelihood × impact


def test_risk_push_is_idempotent(client, tokens):
    token = tokens["rep_quality"]
    node = _node("risk-idem")
    risk_id = str(uuid.uuid4())
    op = {"op_id": f"op-{uuid.uuid4()}", "entity_type": "risk", "entity_id": risk_id,
          "op": "upsert", "base_rev": 0, "payload": _risk_payload(title="خطر مكرر الإرسال")}
    _push(client, token, node, [op])
    _push(client, token, node, [op])
    rows = client.get(RISKS, headers=auth(token)).json()
    assert sum(1 for r in rows if r["id"] == risk_id) == 1


def test_risk_stale_revision_conflicts_not_overwrites(client, tokens):
    token = tokens["rep_quality"]
    node = _node("risk-conflict")
    risk_id = str(uuid.uuid4())
    _push(client, token, node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "risk", "entity_id": risk_id,
         "op": "upsert", "base_rev": 0, "payload": _risk_payload(title="الخطر الأول")},
    ])
    out = _push(client, token, node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "risk", "entity_id": risk_id,
         "op": "upsert", "base_rev": 0, "payload": _risk_payload(title="تعديل قديم")},
    ])
    assert out["results"][0]["status"] == "conflict"
    rows = client.get(RISKS, headers=auth(token)).json()
    row = next(r for r in rows if r["id"] == risk_id)
    assert row["title"] == "الخطر الأول"


def test_risk_rejects_out_of_range_score_inputs(client, tokens):
    node = _node("risk-range")
    out = _push(client, tokens["rep_quality"], node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "risk", "entity_id": str(uuid.uuid4()),
         "op": "upsert", "base_rev": 0, "payload": _risk_payload(likelihood=9)},
    ])
    assert out["results"][0]["status"] == "rejected"
    assert out["results"][0]["reason"] == "validation_failed"


def test_risk_node_cannot_close(client, tokens):
    node = _node("risk-close")
    out = _push(client, tokens["rep_quality"], node, [
        {"op_id": f"op-{uuid.uuid4()}", "entity_type": "risk", "entity_id": str(uuid.uuid4()),
         "op": "upsert", "base_rev": 0, "payload": _risk_payload(status="closed")},
    ])
    assert out["results"][0]["status"] == "rejected"
    assert out["results"][0]["reason"] == "validation_failed"


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------
def test_node_cannot_write_another_hospitals_risk(client, tokens):
    # A Republican user cannot sync for Aljumhouri at all: the API refuses the
    # whole batch (403) before any risk is touched.
    node = _node("risk-cross")
    r = client.post(
        f"{SYNC}/push",
        headers=auth(tokens["rep_quality"]),
        json={
            "node_id": node,
            "hospital_id": str(HOSP_ALJUMHOURI_ID),
            "batch_id": f"batch-{uuid.uuid4()}",
            "operations": [
                {"op_id": f"op-{uuid.uuid4()}", "entity_type": "risk", "entity_id": str(uuid.uuid4()),
                 "op": "upsert", "base_rev": 0, "payload": _risk_payload()},
            ],
        },
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
def test_bootstrap_includes_capa_and_risks(client, tokens):
    node = _node("bootstrap-q")
    out = client.post(
        f"{SYNC}/bootstrap",
        params={"node_id": node, "hospital_id": str(HOSP_REPUBLICAN_ID)},
        headers=auth(tokens["rep_quality"]),
    ).json()
    assert "capa_actions" in out and "risks" in out
    assert all(c["hospital_id"] == str(HOSP_REPUBLICAN_ID) for c in out["capa_actions"])
    assert all(r["hospital_id"] == str(HOSP_REPUBLICAN_ID) for r in out["risks"])
