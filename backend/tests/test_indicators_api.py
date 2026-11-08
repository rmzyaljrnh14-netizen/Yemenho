"""API tests for the indicator library, assignments, values and workflow."""
from __future__ import annotations

import uuid

from app.db.seed_demo import HOSP_ALJUMHOURI_ID, HOSP_REPUBLICAN_ID

from .conftest import auth

INDICATORS = "/api/v1/indicators"
PERIODS = "/api/v1/periods"


def _hospital_indicators(client, token, hospital_id=HOSP_REPUBLICAN_ID):
    r = client.get(f"/api/v1/hospitals/{hospital_id}/indicators", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def _indicator_by_code(client, token, code):
    rows = client.get(INDICATORS, headers=auth(token)).json()
    return next(i for i in rows if i["code"] == code)


def _new_period(client, token, hospital_id=HOSP_REPUBLICAN_ID, month=1, year=2026):
    r = client.post(
        PERIODS,
        headers=auth(token),
        json={"hospital_id": str(hospital_id), "period_type": "monthly", "year": year, "month": month},
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---- Library ----
def test_indicators_require_auth(client):
    assert client.get(INDICATORS).status_code == 401


def test_library_is_seeded(client, tokens):
    rows = client.get(INDICATORS, headers=auth(tokens["central"])).json()
    assert len(rows) >= 25
    codes = {r["code"] for r in rows}
    assert "PS-INF-RATE" in codes
    assert "IPC-HAND" in codes


def test_library_search(client, tokens):
    rows = client.get(INDICATORS, params={"search": "نظافة"}, headers=auth(tokens["central"])).json()
    assert any(r["code"] == "IPC-HAND" for r in rows)


def test_create_indicator_requires_manage(client, tokens):
    payload = {"code": "TMP-TEST-1", "name_ar": "مؤشر اختبار", "computation": "percent"}
    # quality_manager has no indicator.manage
    r = client.post(INDICATORS, headers=auth(tokens["rep_quality"]), json=payload)
    assert r.status_code == 403
    # central_admin does
    r = client.post(INDICATORS, headers=auth(tokens["central"]), json=payload)
    assert r.status_code == 201, r.text
    assert r.json()["code"] == "TMP-TEST-1"


def test_create_indicator_rejects_duplicate_code(client, tokens):
    payload = {"code": "IPC-HAND", "name_ar": "مكرر", "computation": "percent"}
    r = client.post(INDICATORS, headers=auth(tokens["central"]), json=payload)
    assert r.status_code == 409


def test_create_indicator_validates_computation(client, tokens):
    payload = {"code": "BAD-COMP", "name_ar": "خطأ", "computation": "nonsense"}
    r = client.post(INDICATORS, headers=auth(tokens["central"]), json=payload)
    assert r.status_code == 422


# ---- Assignments ----
def test_demo_assignments_exist(client, tokens):
    rows = _hospital_indicators(client, tokens["rep_quality"])
    assert len(rows) >= 20


def test_assign_requires_permission(client, tokens):
    ind = _indicator_by_code(client, tokens["central"], "PS-FALLS")
    body = {"indicator_id": ind["id"], "hospital_id": str(HOSP_REPUBLICAN_ID)}
    # read_only has neither indicator.assign nor entry rights
    r = client.post(f"/api/v1/hospitals/{HOSP_REPUBLICAN_ID}/indicators", headers=auth(tokens["rep_reader"]), json=body)
    assert r.status_code == 403
    # quality_manager may assign
    r = client.post(f"/api/v1/hospitals/{HOSP_REPUBLICAN_ID}/indicators", headers=auth(tokens["rep_quality"]), json=body)
    assert r.status_code == 201, r.text


def test_assign_rejects_department_from_other_hospital(client, tokens):
    # central creates a department in the other hospital
    d = client.post(
        f"/api/v1/hospitals/{HOSP_ALJUMHOURI_ID}/departments",
        headers=auth(tokens["central"]),
        json={"name_ar": "قسم اختبار", "hospital_id": str(HOSP_ALJUMHOURI_ID)},
    )
    assert d.status_code == 201, d.text
    dept_id = d.json()["id"]
    ind = _indicator_by_code(client, tokens["central"], "PS-SSI")
    body = {"indicator_id": ind["id"], "hospital_id": str(HOSP_REPUBLICAN_ID), "department_id": dept_id}
    r = client.post(f"/api/v1/hospitals/{HOSP_REPUBLICAN_ID}/indicators", headers=auth(tokens["rep_quality"]), json=body)
    assert r.status_code == 400


# ---- Periods and values ----
def test_period_requires_enter_permission(client, tokens):
    body = {"hospital_id": str(HOSP_REPUBLICAN_ID), "period_type": "monthly", "year": 2026, "month": 2}
    r = client.post(PERIODS, headers=auth(tokens["rep_reader"]), json=body)
    assert r.status_code == 403


def test_monthly_period_requires_month(client, tokens):
    body = {"hospital_id": str(HOSP_REPUBLICAN_ID), "period_type": "monthly", "year": 2026}
    r = client.post(PERIODS, headers=auth(tokens["rep_quality"]), json=body)
    assert r.status_code == 400


def test_duplicate_period_returns_existing(client, tokens):
    p1 = _new_period(client, tokens["rep_quality"], month=3)
    p2 = _new_period(client, tokens["rep_quality"], month=3)
    assert p1["id"] == p2["id"]


def test_enter_percent_value_computed_and_assessed(client, tokens):
    period = _new_period(client, tokens["rep_quality"], month=4)
    ind = _indicator_by_code(client, tokens["rep_quality"], "IPC-HAND")  # higher_better, target 90
    r = client.put(
        f"{PERIODS}/{period['id']}/values",
        headers=auth(tokens["rep_quality"]),
        json={"indicator_id": ind["id"], "numerator": 92, "denominator": 100},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["value"] == 92.0
    assert body["value_type"] == "computed"

    detail = client.get(f"{PERIODS}/{period['id']}", headers=auth(tokens["rep_quality"])).json()
    val = next(v for v in detail["values"] if v["indicator_id"] == ind["id"])
    assert val["assessment"]["status"] == "good"


def test_zero_denominator_yields_null_value(client, tokens):
    period = _new_period(client, tokens["rep_quality"], month=5)
    ind = _indicator_by_code(client, tokens["rep_quality"], "PS-INF-RATE")  # rate
    r = client.put(
        f"{PERIODS}/{period['id']}/values",
        headers=auth(tokens["rep_quality"]),
        json={"indicator_id": ind["id"], "numerator": 5, "denominator": 0},
    )
    assert r.status_code == 200
    assert r.json()["value"] is None


def test_count_indicator_is_entered(client, tokens):
    period = _new_period(client, tokens["rep_quality"], month=6)
    ind = _indicator_by_code(client, tokens["rep_quality"], "SAFE-TRAIN-N")  # count
    r = client.put(
        f"{PERIODS}/{period['id']}/values",
        headers=auth(tokens["rep_quality"]),
        json={"indicator_id": ind["id"], "entered_value": 3},
    )
    assert r.status_code == 200
    assert r.json()["value"] == 3.0
    assert r.json()["value_type"] == "entered"


def test_value_upsert_records_revisions(client, tokens):
    period = _new_period(client, tokens["rep_quality"], month=7)
    ind = _indicator_by_code(client, tokens["rep_quality"], "IPC-STERIL")
    r1 = client.put(
        f"{PERIODS}/{period['id']}/values",
        headers=auth(tokens["rep_quality"]),
        json={"indicator_id": ind["id"], "numerator": 90, "denominator": 100},
    )
    value_id = r1.json()["id"]
    client.put(
        f"{PERIODS}/{period['id']}/values",
        headers=auth(tokens["rep_quality"]),
        json={"indicator_id": ind["id"], "numerator": 95, "denominator": 100},
    )
    revs = client.get(f"/api/v1/values/{value_id}/revisions", headers=auth(tokens["rep_quality"])).json()
    actions = [x["action"] for x in revs]
    assert "create" in actions and "update" in actions
    assert any(x["old_value"] == 90.0 and x["new_value"] == 95.0 for x in revs)


# ---- Workflow ----
def test_workflow_locks_approved_period(client, tokens):
    period = _new_period(client, tokens["rep_quality"], month=8)
    ind = _indicator_by_code(client, tokens["rep_quality"], "PX-SAT")
    client.put(
        f"{PERIODS}/{period['id']}/values",
        headers=auth(tokens["rep_quality"]),
        json={"indicator_id": ind["id"], "numerator": 80, "denominator": 100},
    )
    assert client.post(f"{PERIODS}/{period['id']}/submit", headers=auth(tokens["rep_quality"])).status_code == 200
    assert client.post(f"{PERIODS}/{period['id']}/approve", headers=auth(tokens["rep_quality"])).status_code == 200

    # Approved data is frozen.
    r = client.put(
        f"{PERIODS}/{period['id']}/values",
        headers=auth(tokens["rep_quality"]),
        json={"indicator_id": ind["id"], "numerator": 99, "denominator": 100},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "period_locked"


def test_return_reopens_period_for_editing(client, tokens):
    period = _new_period(client, tokens["rep_quality"], month=9)
    ind = _indicator_by_code(client, tokens["rep_quality"], "PX-COMPL")
    client.put(
        f"{PERIODS}/{period['id']}/values",
        headers=auth(tokens["rep_quality"]),
        json={"indicator_id": ind["id"], "numerator": 1, "denominator": 100},
    )
    client.post(f"{PERIODS}/{period['id']}/submit", headers=auth(tokens["rep_quality"]))
    r = client.post(f"{PERIODS}/{period['id']}/return", headers=auth(tokens["rep_quality"]))
    assert r.status_code == 200
    assert r.json()["status"] == "returned"
    # editable again
    r = client.put(
        f"{PERIODS}/{period['id']}/values",
        headers=auth(tokens["rep_quality"]),
        json={"indicator_id": ind["id"], "numerator": 2, "denominator": 100},
    )
    assert r.status_code == 200


def test_invalid_transition_rejected(client, tokens):
    period = _new_period(client, tokens["rep_quality"], month=10)
    # draft cannot be approved directly without submit? approve allows submitted/reviewed only
    r = client.post(f"{PERIODS}/{period['id']}/approve", headers=auth(tokens["rep_quality"]))
    assert r.status_code == 409


def test_submit_requires_permission(client, tokens):
    period = _new_period(client, tokens["rep_quality"], month=11)
    r = client.post(f"{PERIODS}/{period['id']}/submit", headers=auth(tokens["rep_reader"]))
    assert r.status_code == 403


# ---- Isolation ----
def test_other_hospital_cannot_read_period(client, tokens):
    period = _new_period(client, tokens["rep_quality"], month=12)
    r = client.get(f"{PERIODS}/{period['id']}", headers=auth(tokens["jum_quality"]))
    assert r.status_code == 404


def test_other_hospital_cannot_write_value(client, tokens):
    period = _new_period(client, tokens["rep_quality"], month=1, year=2027)
    ind = _indicator_by_code(client, tokens["rep_quality"], "QC-UTIL-BED")
    r = client.put(
        f"{PERIODS}/{period['id']}/values",
        headers=auth(tokens["jum_quality"]),
        json={"indicator_id": ind["id"], "numerator": 80, "denominator": 100},
    )
    assert r.status_code == 404


def test_period_list_is_scoped(client, tokens):
    rows = client.get(PERIODS, headers=auth(tokens["jum_quality"])).json()
    # jum.quality has no periods of its own
    assert rows == []
    rep_rows = client.get(PERIODS, headers=auth(tokens["rep_quality"])).json()
    assert len(rep_rows) >= 1
    assert all(r["hospital_id"] == str(HOSP_REPUBLICAN_ID) for r in rep_rows)
