"""Assistant tests (v0.8).

Two layers:
  * pure statistics (no database) — slope, anomaly, direction;
  * the API — national and hospital insights, improvement areas, draft report,
    the optional narrator gating, permissions and per-hospital isolation.

The point of these tests is the honesty rule: every finding must carry the
numbers it came from, and a hospital user must never see another hospital's data.
"""
from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services import ai_narrator, insights
from tests.conftest import login

REP_HOSPITAL = "01900000-0000-7000-8000-0000000000b1"  # H-SANAA-REP
JUM_HOSPITAL = "01900000-0000-7000-8000-0000000000b2"  # H-SANAA-JUM


# ---------------------------------------------------------------------------
# Pure statistics
# ---------------------------------------------------------------------------
def test_linear_slope_basic():
    assert insights.linear_slope([1.0, 2.0, 3.0]) == 1.0
    assert insights.linear_slope([3.0, 2.0, 1.0]) == -1.0
    assert insights.linear_slope([2.0, 2.0, 2.0]) == 0.0
    assert insights.linear_slope([5.0]) is None
    assert insights.linear_slope([]) is None


def test_direction_of_slope():
    assert insights.direction_of_slope(1.0, 10.0) == "up"
    assert insights.direction_of_slope(-1.0, 10.0) == "down"
    assert insights.direction_of_slope(0.05, 10.0) == "flat"
    assert insights.direction_of_slope(None, 10.0) == "unknown"


def test_detect_anomaly_insufficient_data():
    r = insights.detect_anomaly([1.0, 2.0])
    assert r["is_anomaly"] is False
    assert r["reason"] == "insufficient_data"
    assert r["needed"] == insights.MIN_POINTS_ANOMALY


def test_detect_anomaly_spike():
    # A stable history around 10 with a sudden jump to 40 is a clear outlier.
    r = insights.detect_anomaly([10.0, 10.5, 9.5, 10.0, 40.0])
    assert r["is_anomaly"] is True
    assert r["latest"] == 40.0


def test_detect_anomaly_normal_series():
    r = insights.detect_anomaly([10.0, 10.5, 9.5, 10.2, 10.1])
    assert r["is_anomaly"] is False


def test_detect_anomaly_flat_history_then_move():
    r = insights.detect_anomaly([5.0, 5.0, 5.0, 9.0])
    assert r["is_anomaly"] is True
    assert r["reason"] == "deviation_from_flat_history"


# ---------------------------------------------------------------------------
# API — national
# ---------------------------------------------------------------------------
def _h(client: TestClient, username: str = "central.admin") -> dict:
    return {"Authorization": f"Bearer {login(client, username)}"}


def test_assistant_status_reports_not_configured(client: TestClient):
    r = client.get("/api/v1/assistant/status", headers=_h(client))
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    # No model configured in the test environment.
    assert body["model_configured"] is False
    assert body["narrative_available"] is False
    assert body["note_ar"]


def test_national_insights_are_grounded(client: TestClient):
    r = client.get("/api/v1/assistant/national?year=2026", headers=_h(client))
    assert r.status_code == 200
    body = r.json()
    assert body["disclaimer_ar"]
    assert isinstance(body["insights"], list)
    # Every finding must carry its basis, and none may be invented.
    for ins in body["insights"]:
        assert ins["title_ar"]
        assert ins["detail_ar"]
        assert ins["severity"] in ("high", "medium", "info")
        assert "basis" in ins


def test_national_insights_flag_late_hospital(client: TestClient):
    # The demo "other" hospital has no period for this far-future year, so it is
    # flagged as late — derived from real rows, not fabricated.
    r = client.get("/api/v1/assistant/national?year=2030", headers=_h(client))
    assert r.status_code == 200
    kinds = {i["kind"] for i in r.json()["insights"]}
    assert "late_submission" in kinds


# ---------------------------------------------------------------------------
# API — hospital
# ---------------------------------------------------------------------------
def test_hospital_insights_have_numbers(client: TestClient):
    r = client.get(
        f"/api/v1/assistant/hospital/{REP_HOSPITAL}?year=2026", headers=_h(client, "rep.quality")
    )
    assert r.status_code == 200
    body = r.json()
    assert body["hospital_id"] == REP_HOSPITAL
    assert body["disclaimer_ar"]
    for ins in body["insights"]:
        assert ins["basis"]
    # Improvement areas (if any) are real indicator rows with their values.
    for a in body["improvement_areas"]:
        assert a["indicator_code"]
        assert a["assessment_status"] in ("warning", "poor")


def test_hospital_insights_include_quality_pressure(client: TestClient):
    r = client.get(
        f"/api/v1/assistant/hospital/{REP_HOSPITAL}?year=2026", headers=_h(client, "rep.quality")
    )
    kinds = {i["kind"] for i in r.json()["insights"]}
    # The demo hospital has open incidents and open RCA rows.
    assert "open_incidents" in kinds


def test_draft_report_is_plain_arabic(client: TestClient):
    r = client.get(
        f"/api/v1/assistant/hospital/{REP_HOSPITAL}/draft-report?year=2026",
        headers=_h(client, "rep.quality"),
    )
    assert r.status_code == 200
    body = r.json()
    assert "مسودة تقرير أداء" in body["report_text_ar"]
    assert "تحليل آلي مساعد" in body["report_text_ar"]
    assert body["disclaimer_ar"]


# ---------------------------------------------------------------------------
# Permissions and isolation
# ---------------------------------------------------------------------------
def test_hospital_user_cannot_read_another_hospital(client: TestClient):
    r = client.get(
        f"/api/v1/assistant/hospital/{JUM_HOSPITAL}?year=2026", headers=_h(client, "rep.quality")
    )
    assert r.status_code == 403


def test_department_officer_has_no_assistant(client: TestClient):
    # department_officer has no assistant.use permission. Create one on the fly
    # (the demo seed has no department-scope user) and confirm the guard refuses.
    admin = _h(client)
    created = client.post(
        "/api/v1/users",
        headers=admin,
        json={"username": "dept.assistant", "display_name": "مسؤول قسم (اختبار)", "password": "Dept@12345"},
    )
    assert created.status_code in (201, 409), created.text
    user_id = created.json()["id"] if created.status_code == 201 else None
    if user_id is None:
        users = client.get("/api/v1/users", headers=admin).json()
        user_id = next(u["id"] for u in users if u["username"] == "dept.assistant")
    assign = client.post(
        "/api/v1/users/assignments",
        headers=admin,
        json={
            "user_id": user_id,
            "role_code": "department_officer",
            "scope_type": "hospital",
            "scope_id": REP_HOSPITAL,
        },
    )
    assert assign.status_code in (201, 409), assign.text

    token = login(client, "dept.assistant", "Dept@12345")
    r = client.get(
        "/api/v1/assistant/national?year=2026", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 403


def test_assistant_requires_authentication(client: TestClient):
    r = client.get("/api/v1/assistant/national?year=2026")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Optional narrator
# ---------------------------------------------------------------------------
def test_narrator_is_off_without_configuration(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_enabled", False)
    monkeypatch.setattr(settings, "ai_api_key", "")
    assert ai_narrator.is_configured() is False
    assert ai_narrator.narrate({"findings": []}) is None


def test_narrator_parses_a_response(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_api_key", "sk-test")
    monkeypatch.setattr(settings, "ai_model", "test-model")
    assert ai_narrator.is_configured() is True

    def handler(request: httpx.Request) -> httpx.Response:
        assert "test-model" in request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ملخص تجريبي مبني على الأرقام."}}]},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as mock_client:
        out = ai_narrator.narrate({"findings": []}, client=mock_client)
    assert out == "ملخص تجريبي مبني على الأرقام."


def test_narrator_never_raises_on_error(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_api_key", "sk-test")
    monkeypatch.setattr(settings, "ai_model", "test-model")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with httpx.Client(transport=httpx.MockTransport(handler)) as mock_client:
        assert ai_narrator.narrate({"findings": []}, client=mock_client) is None
