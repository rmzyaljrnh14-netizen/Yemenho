"""Configurable alert-rules tests (v0.10).

The thresholds that drive the insight engine are data. These tests check the
catalogue, validation/clamping, scope resolution, permissions and — the point of
the whole feature — that a changed threshold really changes the alerts produced.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.services import alert_rules

REP_HOSPITAL = "01900000-0000-7000-8000-0000000000b1"  # H-SANAA-REP
JUM_HOSPITAL = "01900000-0000-7000-8000-0000000000b2"  # H-SANAA-JUM
YEAR = 2026


def _h(client: TestClient, username: str = "central.admin") -> dict:
    from tests.conftest import login

    return {"Authorization": f"Bearer {login(client, username)}"}


# ---------------------------------------------------------------------------
# Pure validation / clamping
# ---------------------------------------------------------------------------
def test_clamp_keeps_defaults_for_unknown_and_empty():
    assert alert_rules.clamp_params("high_risk", {}) == {"score_threshold": 15}
    assert alert_rules.clamp_params("high_risk", {"nope": 5}) == {"score_threshold": 15}


def test_clamp_bounds_values_and_drops_unknown_keys():
    got = alert_rules.clamp_params("anomaly", {"z_threshold": 99, "min_points": 1, "junk": 7})
    assert got == {"z_threshold": 10.0, "min_points": 3}  # clamped to [1,10] and [3,24]


def test_clamp_low_compliance_high_cannot_exceed_warn():
    got = alert_rules.clamp_params("low_compliance", {"warn_below": 80, "high_below": 95})
    assert got["high_below"] == 80  # pulled down to the warn threshold


# ---------------------------------------------------------------------------
# Catalogue + effective resolution
# ---------------------------------------------------------------------------
def test_catalogue_lists_every_configurable_kind(client: TestClient):
    r = client.get("/api/v1/alert-rules", headers=_h(client))
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "national"
    kinds = {x["kind"] for x in body["rules"]}
    assert kinds == set(alert_rules.CONFIGURABLE_KINDS)
    for rule in body["rules"]:
        assert rule["label_ar"]
        # a toggle-only kind (late_submission) has no numeric parameters
        if alert_rules.DEFAULT_PARAMS[rule["kind"]]:
            assert rule["params_spec"]
        # effective defaults come from the seeded national rows
        assert rule["effective_params"] == rule["national_params"]


def test_national_default_matches_original_engine_constant(client: TestClient):
    r = client.get("/api/v1/alert-rules", headers=_h(client))
    rules = {x["kind"]: x for x in r.json()["rules"]}
    assert rules["low_compliance"]["effective_params"] == {"warn_below": 85, "high_below": 70}
    assert rules["anomaly"]["effective_params"] == {"z_threshold": 3.5, "min_points": 4}
    assert rules["high_risk"]["effective_params"] == {"score_threshold": 15}


# ---------------------------------------------------------------------------
# Writing rules + permissions
# ---------------------------------------------------------------------------
def test_update_national_rule_round_trips(client: TestClient):
    h = _h(client)
    r = client.put(
        "/api/v1/alert-rules/high_risk",
        headers=h,
        json={"params": {"score_threshold": 12}, "is_enabled": True, "note_ar": "خُفِّضت العتبة"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["effective_params"] == {"score_threshold": 12}
    # restore so other tests see the default; the reset must bring back the code default
    reset = client.post("/api/v1/alert-rules/high_risk/reset", headers=h)
    assert reset.status_code == 200, reset.text
    assert reset.json()["effective_params"] == {"score_threshold": 15}


def test_read_only_user_cannot_configure(client: TestClient):
    r = client.put(
        "/api/v1/alert-rules/high_risk",
        headers=_h(client, "rep.reader"),
        json={"params": {"score_threshold": 10}, "is_enabled": True},
    )
    assert r.status_code == 403


def test_unknown_kind_is_rejected(client: TestClient):
    r = client.put(
        "/api/v1/alert-rules/not_a_kind",
        headers=_h(client),
        json={"params": {}, "is_enabled": True},
    )
    assert r.status_code == 404


def test_national_only_kind_cannot_be_overridden(client: TestClient):
    r = client.put(
        f"/api/v1/alert-rules/late_submission?hospital_id={REP_HOSPITAL}",
        headers=_h(client),
        json={"params": {}, "is_enabled": True},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Hospital override
# ---------------------------------------------------------------------------
def test_hospital_override_wins_then_resets(client: TestClient):
    h = _h(client)
    r = client.put(
        f"/api/v1/alert-rules/high_risk?hospital_id={REP_HOSPITAL}",
        headers=h,
        json={"params": {"score_threshold": 9}, "is_enabled": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["hospital_override"] is True
    assert body["hospital_params"] == {"score_threshold": 9}
    assert body["effective_params"] == {"score_threshold": 9}
    assert body["national_params"] == {"score_threshold": 15}

    # another hospital is unaffected
    other = client.get(f"/api/v1/alert-rules?hospital_id={JUM_HOSPITAL}", headers=h).json()
    jum = {x["kind"]: x for x in other["rules"]}["high_risk"]
    assert jum["hospital_override"] is False
    assert jum["effective_params"] == {"score_threshold": 15}

    # reset removes the override
    client.post(f"/api/v1/alert-rules/high_risk/reset?hospital_id={REP_HOSPITAL}", headers=h)
    after = client.get(f"/api/v1/alert-rules?hospital_id={REP_HOSPITAL}", headers=h).json()
    rep = {x["kind"]: x for x in after["rules"]}["high_risk"]
    assert rep["hospital_override"] is False


# ---------------------------------------------------------------------------
# The feature's whole point: a threshold change changes the alerts
# ---------------------------------------------------------------------------
def test_raising_risk_threshold_silences_the_alert(client: TestClient):
    h = _h(client)
    before = client.get(
        f"/api/v1/alerts?year={YEAR}&hospital_id={REP_HOSPITAL}", headers=h
    ).json()
    assert any(a["kind"] == "high_risk" for a in before["alerts"])

    # A score threshold above every seeded open risk (max is 15) yields none.
    client.put(
        f"/api/v1/alert-rules/high_risk?hospital_id={REP_HOSPITAL}",
        headers=h,
        json={"params": {"score_threshold": 25}, "is_enabled": True},
    )
    after = client.get(
        f"/api/v1/alerts?year={YEAR}&hospital_id={REP_HOSPITAL}", headers=h
    ).json()
    assert not any(a["kind"] == "high_risk" for a in after["alerts"])

    client.post(f"/api/v1/alert-rules/high_risk/reset?hospital_id={REP_HOSPITAL}", headers=h)


def test_disabling_a_rule_removes_its_alert(client: TestClient):
    h = _h(client)
    client.put(
        f"/api/v1/alert-rules/high_risk?hospital_id={REP_HOSPITAL}",
        headers=h,
        json={"params": {"score_threshold": 15}, "is_enabled": False},
    )
    after = client.get(
        f"/api/v1/alerts?year={YEAR}&hospital_id={REP_HOSPITAL}", headers=h
    ).json()
    assert not any(a["kind"] == "high_risk" for a in after["alerts"])
    client.post("/api/v1/alert-rules/high_risk/reset?hospital_id=" + REP_HOSPITAL, headers=h)


def test_low_compliance_basis_carries_the_thresholds(client: TestClient):
    r = client.get(f"/api/v1/alerts?year={YEAR}", headers=_h(client))
    assert r.status_code == 200
    for a in r.json()["alerts"]:
        if a["kind"] == "low_compliance":
            assert a["basis"]["warn_below"] == 85
            assert a["basis"]["high_below"] == 70


def test_hospital_user_cannot_touch_another_hospital_rules(client: TestClient):
    r = client.put(
        f"/api/v1/alert-rules/high_risk?hospital_id={JUM_HOSPITAL}",
        headers=_h(client, "rep.quality"),
        json={"params": {"score_threshold": 10}, "is_enabled": True},
    )
    assert r.status_code == 403


def test_national_late_submission_toggle_silences_that_alert(client: TestClient):
    h = _h(client)
    before = client.get(f"/api/v1/alerts?year={YEAR}", headers=h).json()
    assert any(a["kind"] == "late_submission" for a in before["alerts"])

    r = client.put(
        "/api/v1/alert-rules/late_submission",
        headers=h,
        json={"params": {}, "is_enabled": False, "note_ar": "أُوقف مؤقتاً"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is False

    after = client.get(f"/api/v1/alerts?year={YEAR}", headers=h).json()
    assert not any(a["kind"] == "late_submission" for a in after["alerts"])

    client.post("/api/v1/alert-rules/late_submission/reset", headers=h)
    restored = client.get(f"/api/v1/alerts?year={YEAR}", headers=h).json()
    assert any(a["kind"] == "late_submission" for a in restored["alerts"])
