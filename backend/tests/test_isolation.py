"""Data isolation (RLS) tests — the core national security guarantee.

These prove that a hospital user can never read another hospital's data, a
governorate user sees only its governorate, and central sees everything.
"""
from __future__ import annotations

from app.db.seed_demo import HOSP_ALJUMHOURI_ID, HOSP_REPUBLICAN_ID
from tests.conftest import auth

REP = str(HOSP_REPUBLICAN_ID)
JUM = str(HOSP_ALJUMHOURI_ID)


def test_central_sees_all_hospitals(client, tokens):
    r = client.get("/api/v1/hospitals", headers=auth(tokens["central"]))
    assert r.status_code == 200
    codes = {h["code"] for h in r.json()}
    assert {"H-SANAA-REP", "H-SANAA-JUM"} <= codes


def test_hospital_user_sees_only_own_hospital(client, tokens):
    r = client.get("/api/v1/hospitals", headers=auth(tokens["rep_quality"]))
    assert r.status_code == 200
    codes = {h["code"] for h in r.json()}
    assert codes == {"H-SANAA-REP"}


def test_hospital_user_cannot_read_other_hospital_by_id(client, tokens):
    # Direct id access must be blocked (RLS hides the row -> 404, never 200).
    r = client.get(f"/api/v1/hospitals/{JUM}", headers=auth(tokens["rep_quality"]))
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "not_found"


def test_hospital_user_can_read_own_hospital_by_id(client, tokens):
    r = client.get(f"/api/v1/hospitals/{REP}", headers=auth(tokens["rep_quality"]))
    assert r.status_code == 200
    assert r.json()["code"] == "H-SANAA-REP"


def test_other_hospital_user_isolated_too(client, tokens):
    r = client.get("/api/v1/hospitals", headers=auth(tokens["jum_quality"]))
    assert r.status_code == 200
    codes = {h["code"] for h in r.json()}
    assert codes == {"H-SANAA-JUM"}


def test_governorate_sees_its_hospitals_only(client, tokens):
    r = client.get("/api/v1/hospitals", headers=auth(tokens["gov"]))
    assert r.status_code == 200
    codes = {h["code"] for h in r.json()}
    # Both demo hospitals are in Sanaa governorate -> visible.
    assert codes == {"H-SANAA-REP", "H-SANAA-JUM"}


def test_departments_isolated_by_hospital(client, tokens):
    r = client.get(f"/api/v1/hospitals/{REP}/departments", headers=auth(tokens["rep_quality"]))
    assert r.status_code == 200
    assert len(r.json()) >= 4

    # The other hospital has no departments; a cross-hospital read returns nothing.
    r2 = client.get(f"/api/v1/hospitals/{JUM}/departments", headers=auth(tokens["rep_quality"]))
    assert r2.status_code == 200
    assert r2.json() == []
