"""Tests for the national sync monitor (v0.12).

Covers the read views (devices, conflicts, overview), the conflict resolution
action, permission gating, and hospital isolation through row-level security.
"""
from __future__ import annotations

from app.db.seed_demo import HOSP_ALJUMHOURI_ID, HOSP_REPUBLICAN_ID

from .conftest import auth

SM = "/api/v1/sync-monitor"


# ---- Access control ----
def test_requires_auth(client):
    assert client.get(f"{SM}/overview").status_code == 401
    assert client.get(f"{SM}/devices").status_code == 401
    assert client.get(f"{SM}/conflicts").status_code == 401


def test_read_only_user_is_forbidden(client, tokens):
    assert client.get(f"{SM}/overview", headers=auth(tokens["rep_reader"])).status_code == 403
    assert client.get(f"{SM}/devices", headers=auth(tokens["rep_reader"])).status_code == 403


def test_read_only_user_cannot_resolve(client, tokens):
    body = {"resolution": "reviewed"}
    r = client.post(
        f"{SM}/conflicts/01900000-0000-7000-8000-0000000000d1/resolve",
        headers=auth(tokens["rep_reader"]),
        json=body,
    )
    assert r.status_code == 403


# ---- Overview ----
def test_central_overview_counts(client, tokens):
    r = client.get(f"{SM}/overview", headers=auth(tokens["central"]))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["devices_total"] >= 2
    assert data["devices_stale"] >= 1
    assert data["devices_ok"] >= 1
    assert data["open_conflicts"] >= 1
    assert data["stale_days"] == 7


# ---- Devices ----
def test_central_sees_all_devices(client, tokens):
    r = client.get(f"{SM}/devices", headers=auth(tokens["central"]))
    assert r.status_code == 200, r.text
    nodes = {n["node_id"]: n for n in r.json()}
    assert "demo-node-rep-01" in nodes
    assert "demo-node-jum-01" in nodes
    assert nodes["demo-node-jum-01"]["status"] == "stale"
    assert nodes["demo-node-rep-01"]["status"] == "ok"


def test_only_stale_filter(client, tokens):
    r = client.get(f"{SM}/devices?only_stale=true", headers=auth(tokens["central"]))
    nodes = r.json()
    assert all(n["status"] == "stale" for n in nodes)
    assert any(n["node_id"] == "demo-node-jum-01" for n in nodes)


def test_hospital_user_sees_only_own_devices(client, tokens):
    r = client.get(f"{SM}/devices", headers=auth(tokens["rep_quality"]))
    assert r.status_code == 200, r.text
    ids = {n["node_id"] for n in r.json()}
    assert "demo-node-rep-01" in ids
    # The other hospital's device must never appear.
    assert "demo-node-jum-01" not in ids


# ---- Conflicts ----
def test_central_lists_open_conflicts(client, tokens):
    r = client.get(f"{SM}/conflicts", headers=auth(tokens["central"]))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] >= 1
    entry = next(e for e in data["entries"] if e["id"] == "01900000-0000-7000-8000-0000000000d1")
    assert entry["entity_label_ar"] == "قيم المؤشرات"
    assert entry["resolution"] == "auto_server"
    assert entry["local_payload"]["value"] == 91.0
    assert entry["server_payload"]["value"] == 88.5


def test_hospital_user_conflicts_are_scoped(client, tokens):
    r = client.get(f"{SM}/conflicts", headers=auth(tokens["rep_quality"]))
    assert r.status_code == 200, r.text
    for e in r.json()["entries"]:
        assert e["hospital_id"] == str(HOSP_REPUBLICAN_ID)


def test_other_hospital_sees_no_rep_conflict(client, tokens):
    r = client.get(f"{SM}/conflicts", headers=auth(tokens["jum_quality"]))
    assert r.status_code == 200, r.text
    ids = {e["id"] for e in r.json()["entries"]}
    assert "01900000-0000-7000-8000-0000000000d1" not in ids


def test_hospital_user_cannot_request_other_hospital(client, tokens):
    r = client.get(
        f"{SM}/conflicts?hospital_id={HOSP_ALJUMHOURI_ID}",
        headers=auth(tokens["rep_quality"]),
    )
    assert r.status_code == 403


# ---- Resolution ----
def test_resolve_marks_conflict_reviewed(client, tokens):
    cid = "01900000-0000-7000-8000-0000000000d1"
    r = client.post(
        f"{SM}/conflicts/{cid}/resolve",
        headers=auth(tokens["rep_quality"]),
        json={"resolution": "reviewed", "note_ar": "راجع مدير الجودة واعتمد نسخة الخادم."},
    )
    assert r.status_code == 200, r.text
    assert r.json()["resolution"] == "reviewed"

    # It leaves the open list and appears with the resolved flag.
    open_ids = {e["id"] for e in client.get(f"{SM}/conflicts", headers=auth(tokens["central"])).json()["entries"]}
    assert cid not in open_ids
    resolved = client.get(
        f"{SM}/conflicts?include_resolved=true", headers=auth(tokens["central"])
    ).json()["entries"]
    entry = next(e for e in resolved if e["id"] == cid)
    assert entry["resolution"] == "reviewed"
    assert entry["resolved_by_name"] is not None
    assert entry["resolution_label_ar"] == "راجعه مسؤول واعتمده"


def test_resolve_unknown_conflict_is_404(client, tokens):
    r = client.post(
        f"{SM}/conflicts/01900000-0000-7000-8000-00000000ffff/resolve",
        headers=auth(tokens["central"]),
        json={"resolution": "dismissed"},
    )
    assert r.status_code == 404


def test_resolve_bad_resolution_is_422(client, tokens):
    r = client.post(
        f"{SM}/conflicts/01900000-0000-7000-8000-0000000000d1/resolve",
        headers=auth(tokens["central"]),
        json={"resolution": "nonsense"},
    )
    assert r.status_code == 422


def test_resolve_is_audited(client, tokens):
    r = client.get(
        "/api/v1/audit-log?entity_type=sync&action=resolve_conflict",
        headers=auth(tokens["central"]),
    )
    assert r.status_code == 200, r.text
    entries = r.json()["entries"]
    assert any(e["entity_id"] == "01900000-0000-7000-8000-0000000000d1" for e in entries)
