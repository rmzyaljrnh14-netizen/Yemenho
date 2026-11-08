"""API tests for reports, dashboards and exports (v0.5)."""
from __future__ import annotations

from app.db.seed_demo import HOSP_ALJUMHOURI_ID, HOSP_REPUBLICAN_ID

from .conftest import auth

REPORTS = "/api/v1/reports"
PERIODS = "/api/v1/periods"
YEAR = 2025  # a year no other test writes to


def _indicator_by_code(client, token, code):
    rows = client.get("/api/v1/indicators", headers=auth(token)).json()
    return next(i for i in rows if i["code"] == code)


def _period(client, token, hospital_id=HOSP_REPUBLICAN_ID, month=6, year=YEAR):
    r = client.post(
        PERIODS,
        headers=auth(token),
        json={"hospital_id": str(hospital_id), "period_type": "monthly", "year": year, "month": month},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _enter(client, token, period_id, indicator_id, numerator, denominator, department_id=None):
    body = {
        "indicator_id": str(indicator_id),
        "numerator": numerator,
        "denominator": denominator,
    }
    if department_id is not None:
        body["department_id"] = str(department_id)
    r = client.put(f"{PERIODS}/{period_id}/values", headers=auth(token), json=body)
    assert r.status_code == 200, r.text
    return r.json()


# ---- Access control ----
def test_reports_require_auth(client):
    assert client.get(f"{REPORTS}/overview", params={"year": YEAR, "month": 6}).status_code == 401


def test_read_only_can_view_reports(client, tokens):
    r = client.get(f"{REPORTS}/overview", params={"year": YEAR, "month": 6}, headers=auth(tokens["rep_reader"]))
    assert r.status_code == 200, r.text


def test_hospital_user_cannot_view_another_hospital(client, tokens):
    r = client.get(
        f"{REPORTS}/hospital/{HOSP_ALJUMHOURI_ID}",
        params={"year": YEAR, "month": 6},
        headers=auth(tokens["rep_quality"]),
    )
    assert r.status_code == 403


def test_hospital_user_cannot_export_another_hospital(client, tokens):
    r = client.get(
        f"{REPORTS}/export.xlsx",
        params={"year": YEAR, "month": 6, "hospital_id": str(HOSP_ALJUMHOURI_ID)},
        headers=auth(tokens["rep_quality"]),
    )
    assert r.status_code == 403


# ---- Aggregation and honesty ----
def test_overview_is_scoped_for_hospital_user(client, tokens):
    ov = client.get(f"{REPORTS}/overview", params={"year": YEAR, "month": 6}, headers=auth(tokens["rep_quality"])).json()
    assert ov["hospitals_total"] == 1
    assert all(h["hospital_name_ar"] for h in ov["hospitals"])


def test_compliance_counts_only_indicators_with_values(client, tokens):
    token = tokens["rep_quality"]
    period = _period(client, token)
    indicator = _indicator_by_code(client, token, "AUDIT-COVER")
    _enter(client, token, period["id"], indicator["id"], 18, 20)  # 90% -> met (target 90)

    detail = client.get(f"{REPORTS}/hospital/{HOSP_REPUBLICAN_ID}", params={"year": YEAR, "month": 6}, headers=auth(token)).json()
    assert detail["indicators_with_value"] >= 1
    assert detail["indicators_met"] >= 1
    assert detail["indicators_unknown"] >= 0
    # no value is ever invented for indicators that were not entered
    assert detail["indicators_total"] == detail["indicators_with_value"] + detail["indicators_unknown"]


def test_missing_value_is_not_zero(client, tokens):
    token = tokens["rep_quality"]
    detail = client.get(f"{REPORTS}/hospital/{HOSP_REPUBLICAN_ID}", params={"year": 2024, "month": 1}, headers=auth(token)).json()
    # A month with no period at all reports zero coverage, not a fabricated 100%.
    assert detail["period_id"] is None
    assert detail["compliance_percent"] is None
    assert detail["indicators_with_value"] == 0


def test_late_hospitals_lists_unsubmitted(client, tokens):
    token = tokens["rep_quality"]
    _period(client, token, month=8)  # draft, never submitted
    r = client.get(f"{REPORTS}/late", params={"year": YEAR, "month": 8}, headers=auth(token)).json()
    assert len(r["hospitals"]) == 1
    assert r["hospitals"][0]["period_status"] == "draft"
    assert r["hospitals"][0]["status_label_ar"]


def test_submitted_hospital_is_not_late(client, tokens):
    token = tokens["rep_quality"]
    period = _period(client, token, month=9)
    assert client.post(f"{PERIODS}/{period['id']}/submit", headers=auth(token), json={}).status_code == 200
    r = client.get(f"{REPORTS}/late", params={"year": YEAR, "month": 9}, headers=auth(token)).json()
    assert r["hospitals"] == []


def test_compare_orders_by_compliance(client, tokens):
    token = tokens["rep_quality"]
    period = _period(client, token, month=10)
    indicator = _indicator_by_code(client, token, "IPC-HAND")
    _enter(client, token, period["id"], indicator["id"], 95, 100)
    r = client.get(f"{REPORTS}/compare", params={"year": YEAR, "month": 10}, headers=auth(token)).json()
    assert len(r["hospitals"]) == 1
    assert r["hospitals"][0]["compliance_percent"] is not None


def test_trend_returns_series(client, tokens):
    token = tokens["rep_quality"]
    indicator = _indicator_by_code(client, token, "IPC-HAND")
    p1 = _period(client, token, month=11)
    p2 = _period(client, token, month=12)
    _enter(client, token, p1["id"], indicator["id"], 80, 100)
    _enter(client, token, p2["id"], indicator["id"], 90, 100)
    # A wide window so other tests' periods (later years) do not crowd these out.
    r = client.get(
        f"{REPORTS}/trend",
        params={"indicator_id": str(indicator["id"]), "months": 36},
        headers=auth(token),
    ).json()
    values = [p["value"] for p in r["points"]]
    assert 80.0 in values and 90.0 in values
    assert [p["period_label"] for p in r["points"]] == sorted(p["period_label"] for p in r["points"])


# ---- Exports ----
def test_export_xlsx_is_a_real_workbook(client, tokens):
    r = client.get(f"{REPORTS}/export.xlsx", params={"year": YEAR, "month": 6}, headers=auth(tokens["rep_quality"]))
    assert r.status_code == 200
    assert r.content[:2] == b"PK"  # zip magic -> xlsx
    assert "spreadsheetml" in r.headers["content-type"]


def test_export_pdf_is_a_real_pdf(client, tokens):
    r = client.get(f"{REPORTS}/export.pdf", params={"year": YEAR, "month": 6}, headers=auth(tokens["rep_quality"]))
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"
    assert r.headers["content-type"] == "application/pdf"
