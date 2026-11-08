"""Offline sync for internal audits and improvement plans (v0.15).

A hospital must be able to open an internal audit and draft an improvement plan
(with its actions) with no internet. All three join the sync protocol in docs/14
exactly as incidents, CAPA and risks do: unique op_id idempotency, a revision
counter so a stale push is a conflict (never a silent overwrite), server-owned
codes and sign-off, and full hospital isolation (an action is scoped through its
parent plan).
"""
from __future__ import annotations

import uuid

from app.db.seed_demo import HOSP_ALJUMHOURI_ID, HOSP_REPUBLICAN_ID

from .conftest import auth

SYNC = "/api/v1/sync"
AUDITS = "/api/v1/quality/audits"
PLANS = "/api/v1/quality/plans"


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


def _op(entity_type: str, entity_id: str, payload: dict, base_rev: int = 0, op: str = "upsert") -> dict:
    return {
        "op_id": f"op-{uuid.uuid4()}",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "op": op,
        "base_rev": base_rev,
        "payload": payload,
    }


def _audit_payload(**over) -> dict:
    base = {
        "title": "تدقيق داخلي من جهاز دون اتصال",
        "standard_ar": "معايير مكافحة العدوى",
        "scope_ar": "قسم العمليات",
        "auditor_name_ar": "فريق الجودة",
        "audit_date": "2026-06-15",
        "status": "planned",
    }
    base.update(over)
    return base


def _plan_payload(**over) -> dict:
    base = {
        "title": "خطة تحسين من جهاز دون اتصال",
        "objective_ar": "تقليل زمن الانتظار في الطوارئ",
        "baseline_ar": "٤٥ دقيقة",
        "target_ar": "٢٠ دقيقة",
        "owner_name_ar": "مدير الجودة",
        "start_date": "2026-06-01",
        "due_date": "2026-09-01",
        "status": "draft",
    }
    base.update(over)
    return base


def _action_payload(plan_id: str, **over) -> dict:
    base = {
        "plan_id": plan_id,
        "title": "خطوة تنفيذية من جهاز دون اتصال",
        "owner_name_ar": "مسؤول القسم",
        "due_date": "2026-07-01",
        "note_ar": "متابعة أسبوعية",
        "status": "open",
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Internal audits
# ---------------------------------------------------------------------------
def test_audit_created_offline_is_applied(client, tokens):
    node = _node("audit")
    audit_id = str(uuid.uuid4())
    out = _push(client, tokens["rep_quality"], node, [_op("audit", audit_id, _audit_payload())])
    result = out["results"][0]
    assert result["status"] == "applied"
    assert result["new_rev"] == 1

    listed = client.get(AUDITS, headers=auth(tokens["rep_quality"])).json()
    row = next(a for a in listed if a["id"] == audit_id)
    assert row["title"] == "تدقيق داخلي من جهاز دون اتصال"
    assert row["status"] == "planned"
    assert row["code"].startswith("AUD-")


def test_audit_push_is_idempotent(client, tokens):
    node = _node("audit-idem")
    audit_id = str(uuid.uuid4())
    op = _op("audit", audit_id, _audit_payload())
    _push(client, tokens["rep_quality"], node, [op])
    _push(client, tokens["rep_quality"], node, [op])
    listed = client.get(AUDITS, headers=auth(tokens["rep_quality"])).json()
    assert sum(1 for a in listed if a["id"] == audit_id) == 1


def test_audit_stale_revision_conflicts_not_overwrites(client, tokens):
    node = _node("audit-conf")
    audit_id = str(uuid.uuid4())
    _push(client, tokens["rep_quality"], node, [_op("audit", audit_id, _audit_payload())])
    out = _push(
        client, tokens["rep_quality"], node,
        [_op("audit", audit_id, _audit_payload(title="عنوان ثانٍ متأخر"), base_rev=0)],
    )
    assert out["results"][0]["status"] == "conflict"
    listed = client.get(AUDITS, headers=auth(tokens["rep_quality"])).json()
    row = next(a for a in listed if a["id"] == audit_id)
    assert row["title"] == "تدقيق داخلي من جهاز دون اتصال"


def test_audit_node_cannot_complete_itself(client, tokens):
    node = _node("audit-signoff")
    out = _push(
        client, tokens["rep_quality"], node,
        [_op("audit", str(uuid.uuid4()), _audit_payload(status="completed"))],
    )
    assert out["results"][0]["status"] == "rejected"
    assert out["results"][0]["reason"] == "validation_failed"


def test_audit_rejects_short_title(client, tokens):
    node = _node("audit-bad")
    out = _push(client, tokens["rep_quality"], node, [_op("audit", str(uuid.uuid4()), _audit_payload(title="x"))])
    assert out["results"][0]["status"] == "rejected"
    assert out["results"][0]["reason"] == "validation_failed"


# ---------------------------------------------------------------------------
# Improvement plans
# ---------------------------------------------------------------------------
def test_plan_created_offline_is_applied(client, tokens):
    node = _node("plan")
    plan_id = str(uuid.uuid4())
    out = _push(client, tokens["rep_quality"], node, [_op("improvement_plan", plan_id, _plan_payload())])
    assert out["results"][0]["status"] == "applied"

    listed = client.get(PLANS, headers=auth(tokens["rep_quality"])).json()
    row = next(p for p in listed if p["id"] == plan_id)
    assert row["title"] == "خطة تحسين من جهاز دون اتصال"
    assert row["status"] == "draft"
    assert row["code"].startswith("IMP-")


def test_plan_push_is_idempotent(client, tokens):
    node = _node("plan-idem")
    plan_id = str(uuid.uuid4())
    op = _op("improvement_plan", plan_id, _plan_payload())
    _push(client, tokens["rep_quality"], node, [op])
    _push(client, tokens["rep_quality"], node, [op])
    listed = client.get(PLANS, headers=auth(tokens["rep_quality"])).json()
    assert sum(1 for p in listed if p["id"] == plan_id) == 1


def test_plan_stale_revision_conflicts_not_overwrites(client, tokens):
    node = _node("plan-conf")
    plan_id = str(uuid.uuid4())
    _push(client, tokens["rep_quality"], node, [_op("improvement_plan", plan_id, _plan_payload())])
    out = _push(
        client, tokens["rep_quality"], node,
        [_op("improvement_plan", plan_id, _plan_payload(title="عنوان خطة متأخر"), base_rev=0)],
    )
    assert out["results"][0]["status"] == "conflict"
    listed = client.get(PLANS, headers=auth(tokens["rep_quality"])).json()
    row = next(p for p in listed if p["id"] == plan_id)
    assert row["title"] == "خطة تحسين من جهاز دون اتصال"


def test_plan_node_cannot_complete_itself(client, tokens):
    node = _node("plan-signoff")
    out = _push(
        client, tokens["rep_quality"], node,
        [_op("improvement_plan", str(uuid.uuid4()), _plan_payload(status="completed"))],
    )
    assert out["results"][0]["status"] == "rejected"
    assert out["results"][0]["reason"] == "validation_failed"


# ---------------------------------------------------------------------------
# Improvement actions (scoped through their plan)
# ---------------------------------------------------------------------------
def test_plan_action_created_offline_is_applied(client, tokens):
    node = _node("action")
    plan_id = str(uuid.uuid4())
    _push(client, tokens["rep_quality"], node, [_op("improvement_plan", plan_id, _plan_payload())])
    action_id = str(uuid.uuid4())
    out = _push(
        client, tokens["rep_quality"], node,
        [_op("improvement_action", action_id, _action_payload(plan_id))],
    )
    assert out["results"][0]["status"] == "applied"

    detail = client.get(f"{PLANS}/{plan_id}", headers=auth(tokens["rep_quality"])).json()
    assert any(a["id"] == action_id for a in detail["actions"])


def test_plan_action_needs_a_plan(client, tokens):
    node = _node("action-noplan")
    payload = _action_payload(str(uuid.uuid4()))
    out = _push(client, tokens["rep_quality"], node, [_op("improvement_action", str(uuid.uuid4()), payload)])
    assert out["results"][0]["status"] == "rejected"
    assert out["results"][0]["reason"] == "forbidden"


def test_plan_action_cannot_move_between_plans(client, tokens):
    # Once created under a plan, an action may not be re-pointed at another plan.
    node = _node("action-move")
    plan_a = str(uuid.uuid4())
    plan_b = str(uuid.uuid4())
    _push(client, tokens["rep_quality"], node, [
        _op("improvement_plan", plan_a, _plan_payload()),
        _op("improvement_plan", plan_b, _plan_payload(title="خطة ثانية")),
    ])
    action_id = str(uuid.uuid4())
    first = _push(client, tokens["rep_quality"], node, [_op("improvement_action", action_id, _action_payload(plan_a))])
    assert first["results"][0]["status"] == "applied"
    out = _push(
        client, tokens["rep_quality"], node,
        [_op("improvement_action", action_id, _action_payload(plan_b), base_rev=1)],
    )
    assert out["results"][0]["status"] == "rejected"
    assert out["results"][0]["reason"] == "validation_failed"


def test_node_cannot_write_another_hospitals_audit(client, tokens):
    node = _node("audit-cross")
    r = client.post(
        f"{SYNC}/push",
        headers=auth(tokens["rep_quality"]),
        json={
            "node_id": node,
            "hospital_id": str(HOSP_ALJUMHOURI_ID),
            "batch_id": f"batch-{uuid.uuid4()}",
            "operations": [_op("audit", str(uuid.uuid4()), _audit_payload())],
        },
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
def test_bootstrap_includes_audits_and_plans(client, tokens):
    node = _node("bootstrap-ap")
    out = client.post(
        f"{SYNC}/bootstrap",
        params={"node_id": node, "hospital_id": str(HOSP_REPUBLICAN_ID)},
        headers=auth(tokens["rep_quality"]),
    ).json()
    assert "audits" in out and "improvement_plans" in out and "improvement_actions" in out
    assert all(a["hospital_id"] == str(HOSP_REPUBLICAN_ID) for a in out["audits"])
    assert all(p["hospital_id"] == str(HOSP_REPUBLICAN_ID) for p in out["improvement_plans"])
    assert all(a["hospital_id"] == str(HOSP_REPUBLICAN_ID) for a in out["improvement_actions"])
