"""Alert-centre tests (v0.9).

The alert list is *computed* from stored rows, so these tests check the honesty
and the plumbing:

  * keys are stable across recomputations and unique per alert;
  * the list is grounded (every alert carries a basis and a real source);
  * acknowledging persists, is idempotent and reopens cleanly;
  * a read-only user can see the list but cannot acknowledge;
  * a hospital user never sees another hospital's alerts.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.services import alerts

REP_HOSPITAL = "01900000-0000-7000-8000-0000000000b1"  # H-SANAA-REP
JUM_HOSPITAL = "01900000-0000-7000-8000-0000000000b2"  # H-SANAA-JUM
YEAR = 2026


def _h(client: TestClient, username: str = "central.admin") -> dict:
    from tests.conftest import login

    return {"Authorization": f"Bearer {login(client, username)}"}


# ---------------------------------------------------------------------------
# Pure key building
# ---------------------------------------------------------------------------
def test_alert_key_is_stable_and_unique():
    import uuid

    hosp = uuid.UUID(REP_HOSPITAL)
    a = alerts.alert_key("late_submission", hosp, 2026, 5, "")
    b = alerts.alert_key("late_submission", hosp, 2026, 5, "")
    assert a == b  # same identity -> same key across recomputations
    assert a.startswith("late_submission-")
    # Different indicator / hospital / period -> different key.
    assert a != alerts.alert_key("late_submission", hosp, 2026, 5, "IND-1")
    assert a != alerts.alert_key("late_submission", hosp, 2026, 6, "")
    assert a != alerts.alert_key("anomaly", hosp, 2026, 5, "")


# ---------------------------------------------------------------------------
# Reading the list
# ---------------------------------------------------------------------------
def test_national_alerts_are_grounded(client: TestClient):
    r = client.get(f"/api/v1/alerts?year={YEAR}", headers=_h(client))
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "national"
    assert body["summary"]["total"] == len(body["alerts"])
    for a in body["alerts"]:
        assert a["title_ar"] and a["detail_ar"]
        assert a["severity"] in ("high", "medium", "info")
        assert a["source"] in ("indicators", "submission", "quality", "sync")
        assert a["source_label_ar"]
        assert a["key"]


def test_national_alerts_flag_late_hospital(client: TestClient):
    # A far-future year means the demo hospital has no period: a real late alert.
    r = client.get("/api/v1/alerts?year=2030", headers=_h(client))
    assert r.status_code == 200
    kinds = {a["kind"] for a in r.json()["alerts"]}
    assert "late_submission" in kinds


def test_alert_keys_are_unique_within_a_list(client: TestClient):
    r = client.get(f"/api/v1/alerts?year={YEAR}", headers=_h(client))
    keys = [a["key"] for a in r.json()["alerts"]]
    assert len(keys) == len(set(keys))


def test_hospital_scope_returns_only_that_hospital(client: TestClient):
    r = client.get(
        f"/api/v1/alerts?year={YEAR}&hospital_id={REP_HOSPITAL}", headers=_h(client)
    )
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "hospital"
    for a in body["alerts"]:
        assert a["hospital_id"] in (None, REP_HOSPITAL)


# ---------------------------------------------------------------------------
# Acknowledgement
# ---------------------------------------------------------------------------
def _first_hospital_alert(client: TestClient, username: str = "rep.quality") -> dict:
    r = client.get(
        f"/api/v1/alerts?year={YEAR}&hospital_id={REP_HOSPITAL}", headers=_h(client, username)
    )
    assert r.status_code == 200
    alerts_list = r.json()["alerts"]
    return next(a for a in alerts_list if a["hospital_id"] == REP_HOSPITAL)


def test_acknowledge_then_reopen(client: TestClient):
    target = _first_hospital_alert(client)
    assert target["acked"] is False

    ack = client.post(
        f"/api/v1/alerts/{target['key']}/ack?year={YEAR}&hospital_id={REP_HOSPITAL}",
        headers=_h(client, "rep.quality"),
        json={"note_ar": "تمت المراجعة مع مدير الجودة."},
    )
    assert ack.status_code == 200, ack.text
    body = ack.json()
    assert body["acked"] is True
    assert body["note_ar"] == "تمت المراجعة مع مدير الجودة."
    assert body["acked_by_name"]

    # Re-reading the list shows the acknowledgement persisted.
    again = client.get(
        f"/api/v1/alerts?year={YEAR}&hospital_id={REP_HOSPITAL}", headers=_h(client, "rep.quality")
    ).json()["alerts"]
    row = next(a for a in again if a["key"] == target["key"])
    assert row["acked"] is True
    assert row["acked_by_name"]

    # Reopen: the acknowledgement is soft-deleted and the alert shows again.
    reopened = client.post(
        f"/api/v1/alerts/{target['key']}/reopen?year={YEAR}&hospital_id={REP_HOSPITAL}",
        headers=_h(client, "rep.quality"),
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["acked"] is False


def test_acknowledge_is_idempotent(client: TestClient):
    target = _first_hospital_alert(client)
    url = f"/api/v1/alerts/{target['key']}/ack?year={YEAR}&hospital_id={REP_HOSPITAL}"
    first = client.post(url, headers=_h(client, "rep.quality"), json={"note_ar": "أولى"})
    assert first.status_code == 200
    second = client.post(url, headers=_h(client, "rep.quality"), json={"note_ar": "ثانية"})
    assert second.status_code == 200
    # The note is updated, not duplicated.
    assert second.json()["note_ar"] == "ثانية"
    rows = client.get(
        f"/api/v1/alerts?year={YEAR}&hospital_id={REP_HOSPITAL}", headers=_h(client, "rep.quality")
    ).json()["alerts"]
    assert sum(1 for a in rows if a["key"] == target["key"]) == 1


def test_include_acked_false_hides_acknowledged(client: TestClient):
    target = _first_hospital_alert(client)
    client.post(
        f"/api/v1/alerts/{target['key']}/ack?year={YEAR}&hospital_id={REP_HOSPITAL}",
        headers=_h(client, "rep.quality"),
        json={},
    )
    only_open = client.get(
        f"/api/v1/alerts?year={YEAR}&hospital_id={REP_HOSPITAL}&include_acked=false",
        headers=_h(client, "rep.quality"),
    ).json()["alerts"]
    assert all(a["acked"] is False for a in only_open)
    assert target["key"] not in {a["key"] for a in only_open}
    # Clean up so other tests start fresh.
    client.post(
        f"/api/v1/alerts/{target['key']}/reopen?year={YEAR}&hospital_id={REP_HOSPITAL}",
        headers=_h(client, "rep.quality"),
    )


def test_acknowledge_unknown_alert_is_404(client: TestClient):
    r = client.post(
        f"/api/v1/alerts/does-not-exist/ack?year={YEAR}&hospital_id={REP_HOSPITAL}",
        headers=_h(client, "rep.quality"),
        json={},
    )
    assert r.status_code == 404


def test_note_too_long_is_rejected(client: TestClient):
    target = _first_hospital_alert(client)
    r = client.post(
        f"/api/v1/alerts/{target['key']}/ack?year={YEAR}&hospital_id={REP_HOSPITAL}",
        headers=_h(client, "rep.quality"),
        json={"note_ar": "ط" * 501},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Permissions and isolation
# ---------------------------------------------------------------------------
def test_read_only_can_view_but_not_acknowledge(client: TestClient):
    listing = client.get(
        f"/api/v1/alerts?year={YEAR}&hospital_id={REP_HOSPITAL}", headers=_h(client, "rep.reader")
    )
    assert listing.status_code == 200  # report.view is enough to see the list

    target = _first_hospital_alert(client, "rep.reader")
    r = client.post(
        f"/api/v1/alerts/{target['key']}/ack?year={YEAR}&hospital_id={REP_HOSPITAL}",
        headers=_h(client, "rep.reader"),
        json={},
    )
    assert r.status_code == 403  # alert.manage is required to change it


def test_hospital_user_cannot_read_another_hospital(client: TestClient):
    r = client.get(
        f"/api/v1/alerts?year={YEAR}&hospital_id={JUM_HOSPITAL}", headers=_h(client, "rep.quality")
    )
    assert r.status_code == 403


def test_hospital_user_defaults_to_own_hospital(client: TestClient):
    r = client.get(f"/api/v1/alerts?year={YEAR}", headers=_h(client, "rep.quality"))
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "hospital"
    for a in body["alerts"]:
        assert a["hospital_id"] in (None, REP_HOSPITAL)


def test_alerts_require_authentication(client: TestClient):
    r = client.get(f"/api/v1/alerts?year={YEAR}")
    assert r.status_code == 401
