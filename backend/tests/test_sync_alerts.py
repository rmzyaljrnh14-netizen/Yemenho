"""Sync-health alerts (v0.13).

The alert centre now also surfaces sync problems the ministry must see:

  * a hospital device that has not synced for the configured number of days;
  * sync conflicts that no one has reviewed yet.

Both are computed from real ``sync_nodes`` / ``conflict_log`` rows and respect
the configurable thresholds, RLS and hospital isolation.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.seed_demo import HOSP_ALJUMHOURI_ID, HOSP_REPUBLICAN_ID

YEAR = 2026
REP = str(HOSP_REPUBLICAN_ID)
JUM = str(HOSP_ALJUMHOURI_ID)


def _h(client: TestClient, username: str = "central.admin") -> dict:
    from tests.conftest import login

    return {"Authorization": f"Bearer {login(client, username)}"}


def _alerts(client: TestClient, username: str = "central.admin", hospital_id: str | None = None) -> list[dict]:
    q = f"/api/v1/alerts?year={YEAR}"
    if hospital_id:
        q += f"&hospital_id={hospital_id}"
    r = client.get(q, headers=_h(client, username))
    assert r.status_code == 200, r.text
    return r.json()["alerts"]


def _kinds(alerts: list[dict]) -> set[str]:
    return {a["kind"] for a in alerts}


# ---------------------------------------------------------------------------
# Stale device
# ---------------------------------------------------------------------------
def test_stale_device_alert_is_raised(client: TestClient):
    alerts = _alerts(client)
    stale = [a for a in alerts if a["kind"] == "stale_device"]
    assert stale, "expected a stale-device alert for the demo stale node"
    a = stale[0]
    assert a["hospital_id"] == JUM
    assert a["source"] == "sync"
    assert a["source_label_ar"] == "المزامنة"
    # Honest basis: the numbers it was derived from.
    assert a["basis"]["stale_days"] == 7
    assert a["basis"]["days_since_seen"] >= 7


def test_healthy_device_does_not_alert(client: TestClient):
    # The Republican device was seen 3 hours ago: no stale alert for it.
    alerts = _alerts(client)
    stale_hospitals = {a["hospital_id"] for a in alerts if a["kind"] == "stale_device"}
    assert REP not in stale_hospitals


def test_stale_threshold_is_configurable(client: TestClient):
    # Raise the national threshold to 30 days: the 21-day stale device no longer
    # trips it.
    body = {"params": {"stale_days": 30}, "is_enabled": True}
    r = client.put("/api/v1/alert-rules/stale_device", headers=_h(client), json=body)
    assert r.status_code == 200, r.text
    try:
        alerts = _alerts(client)
        assert "stale_device" not in _kinds(alerts)
    finally:
        client.post("/api/v1/alert-rules/stale_device/reset", headers=_h(client))
    # After reset the alert is back.
    assert "stale_device" in _kinds(_alerts(client))


def test_device_never_seen_is_stale(client: TestClient):
    # A node with no last_seen_at is honestly reported as "never seen" and stale.
    from app.db.base import AdminSessionLocal
    from app.models.core import SyncNode

    node_id = "test-node-never-seen"
    db = AdminSessionLocal()
    try:
        if db.get(SyncNode, node_id) is None:
            db.add(SyncNode(node_id=node_id, hospital_id=HOSP_REPUBLICAN_ID, name="جهاز اختبار"))
            db.commit()
    finally:
        db.close()
    try:
        stale = [
            a
            for a in _alerts(client)
            if a["kind"] == "stale_device" and a["basis"]["node_id"] == node_id
        ]
        assert stale, "a never-seen device must be flagged stale"
        assert stale[0]["basis"]["days_since_seen"] is None
    finally:
        db = AdminSessionLocal()
        try:
            row = db.get(SyncNode, node_id)
            if row is not None:
                db.delete(row)
                db.commit()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Open conflict
# ---------------------------------------------------------------------------
def test_open_conflict_alert_is_raised(client: TestClient):
    alerts = _alerts(client)
    conflicts = [a for a in alerts if a["kind"] == "open_conflict"]
    assert conflicts, "expected an open-conflict alert for the demo conflict"
    a = conflicts[0]
    assert a["hospital_id"] == REP
    assert a["source"] == "sync"
    assert a["basis"]["open_conflict_count"] >= 1


def test_resolving_conflict_clears_the_alert(client: TestClient):
    # Create a dedicated conflict on the Aljumhouri hospital (which has none by
    # default), watch the alert appear, resolve it as that hospital's quality
    # manager, then watch the alert disappear. Isolated so it never disturbs the
    # shared demo conflict.
    import uuid

    from app.db.base import AdminSessionLocal
    from app.models.core import ConflictLog

    cid = uuid.UUID("01900000-0000-7000-8000-0000000000d2")
    db = AdminSessionLocal()
    try:
        if db.get(ConflictLog, cid) is None:
            db.add(
                ConflictLog(
                    id=cid,
                    entity_type="indicator_value",
                    entity_id="01900000-0000-7000-8000-0000000000e2",
                    node_id="demo-node-jum-01",
                    hospital_id=HOSP_ALJUMHOURI_ID,
                    local_payload={"value": 12.0},
                    server_payload={"value": 10.0},
                    resolution="auto_server",
                )
            )
            db.commit()
    finally:
        db.close()

    try:
        before = [a for a in _alerts(client) if a["kind"] == "open_conflict"]
        assert any(a["hospital_id"] == JUM for a in before)

        r = client.post(
            f"/api/v1/sync-monitor/conflicts/{cid}/resolve",
            headers=_h(client, "jum.quality"),
            json={"resolution": "reviewed"},
        )
        assert r.status_code == 200, r.text
        after = [a for a in _alerts(client) if a["kind"] == "open_conflict"]
        assert not any(a["hospital_id"] == JUM for a in after)
    finally:
        db = AdminSessionLocal()
        try:
            row = db.get(ConflictLog, cid)
            if row is not None:
                db.delete(row)
                db.commit()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Isolation and permission
# ---------------------------------------------------------------------------
def test_hospital_scope_only_sees_own_sync_alerts(client: TestClient):
    alerts = _alerts(client, username="rep.quality")
    for a in alerts:
        assert a["hospital_id"] in (None, REP)
    # The other hospital's stale device must never surface here.
    assert not any(a["kind"] == "stale_device" and a["hospital_id"] == JUM for a in alerts)


def test_sync_alerts_respect_national_switch(client: TestClient):
    body = {"params": {}, "is_enabled": False}
    r = client.put("/api/v1/alert-rules/stale_device", headers=_h(client), json=body)
    assert r.status_code == 200, r.text
    try:
        assert "stale_device" not in _kinds(_alerts(client))
    finally:
        client.post("/api/v1/alert-rules/stale_device/reset", headers=_h(client))
