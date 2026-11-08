"""Quality and patient-safety API tests (v0.7).

Cover the full loop: report an incident, run an RCA with typed causes, raise
CAPA, register risks (score computed by the database), run an audit, plan
improvements, approve a document, hold a meeting with decisions — then check the
summary, the audit trail, permissions and per-hospital isolation.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import login

REP_HOSPITAL = "01900000-0000-7000-8000-0000000000b1"  # H-SANAA-REP
JUM_HOSPITAL = "01900000-0000-7000-8000-0000000000b2"  # H-SANAA-JUM


def _quality_headers(client: TestClient) -> dict:
    token = login(client, "rep.quality")
    return {"Authorization": f"Bearer {token}"}


# ---- seeded demo data is visible -----------------------------------------
def test_seeded_quality_data_is_listed(client: TestClient):
    h = _quality_headers(client)
    incidents = client.get("/api/v1/quality/incidents", headers=h)
    assert incidents.status_code == 200
    codes = {i["code"] for i in incidents.json()}
    assert "INC-2026-0001" in codes
    assert all(i["hospital_id"] == REP_HOSPITAL for i in incidents.json())

    risks = client.get("/api/v1/quality/risks", headers=h).json()
    assert any(r["code"] == "RSK-2026-0001" for r in risks)
    # score is computed by the database, never sent by the client
    assert all(r["score"] == r["likelihood"] * r["impact"] for r in risks)

    docs = client.get("/api/v1/quality/documents", headers=h).json()
    assert any(d["status"] == "approved" for d in docs)

    meetings = client.get("/api/v1/quality/meetings", headers=h).json()
    assert any(m["status"] == "held" for m in meetings)


def test_rca_detail_includes_typed_causes(client: TestClient):
    h = _quality_headers(client)
    incidents = client.get("/api/v1/quality/incidents", headers=h).json()
    fall = next(i for i in incidents if i["incident_type"] == "fall")
    rca = client.get(f"/api/v1/quality/incidents/{fall['id']}/rca", headers=h)
    assert rca.status_code == 200
    body = rca.json()
    assert body["rca"]["method"] == "five_whys"
    assert len(body["causes"]) == 3
    assert any(c["is_root_cause"] for c in body["causes"])
    assert {c["category"] for c in body["causes"]} == {"process", "environment", "training"}


# ---- full incident -> RCA -> CAPA loop ------------------------------------
def test_incident_rca_capa_loop(client: TestClient):
    h = _quality_headers(client)

    created = client.post(
        "/api/v1/quality/incidents",
        headers=h,
        json={
            "title": "حادث اختباري لمسار العمل",
            "incident_type": "surgical",
            "severity": "major",
            "patient_harm": "severe",
            "immediate_action": "تم إيقاف العملية وتقييم المريض.",
        },
    )
    assert created.status_code == 201, created.text
    incident = created.json()
    assert incident["hospital_id"] == REP_HOSPITAL
    assert incident["code"].startswith("INC-")
    assert incident["status"] == "reported"

    # Creating an RCA moves the incident into the rca stage.
    rca = client.post(
        f"/api/v1/quality/incidents/{incident['id']}/rca",
        headers=h,
        json={"method": "fishbone", "team_ar": "فريق اختباري"},
    )
    assert rca.status_code == 201, rca.text
    rca_id = rca.json()["id"]
    assert client.get(f"/api/v1/quality/incidents/{incident['id']}", headers=h).json()["status"] == "rca"

    # A second RCA for the same incident is refused.
    assert client.post(
        f"/api/v1/quality/incidents/{incident['id']}/rca", headers=h, json={}
    ).status_code == 400

    cause = client.post(
        f"/api/v1/quality/rca/{rca_id}/causes",
        headers=h,
        json={"category": "communication", "description_ar": "تسليم معلومات ناقص بين الفريقين.", "is_root_cause": True},
    )
    assert cause.status_code == 201
    assert cause.json()["is_root_cause"] is True

    # CAPA linked to the incident + RCA; the incident moves to the capa stage.
    capa = client.post(
        "/api/v1/quality/capa",
        headers=h,
        json={
            "incident_id": incident["id"],
            "rca_id": rca_id,
            "kind": "corrective",
            "title": "تحديث بروتوكول التسليم",
            "priority": "critical",
            "due_date": "2026-06-30",
        },
    )
    assert capa.status_code == 201, capa.text
    capa_id = capa.json()["id"]
    assert client.get(f"/api/v1/quality/incidents/{incident['id']}", headers=h).json()["status"] == "capa"

    # Completing and verifying the CAPA stamps the times.
    done = client.patch(
        f"/api/v1/quality/capa/{capa_id}", headers=h, json={"status": "done", "completion_note_ar": "أُنجز."}
    )
    assert done.status_code == 200
    assert done.json()["completed_at"] is not None
    verified = client.patch(f"/api/v1/quality/capa/{capa_id}", headers=h, json={"status": "verified"})
    assert verified.json()["verified_at"] is not None

    # Close the incident.
    closed = client.post(
        f"/api/v1/quality/incidents/{incident['id']}/status", headers=h, json={"status": "closed"}
    )
    assert closed.json()["closed_at"] is not None
    # A closed incident cannot be edited.
    assert client.patch(
        f"/api/v1/quality/incidents/{incident['id']}", headers=h, json={"title": "تعديل مرفوض"}
    ).status_code == 400


def test_capa_overdue_flag(client: TestClient):
    h = _quality_headers(client)
    created = client.post(
        "/api/v1/quality/capa",
        headers=h,
        json={"title": "إجراء متأخر اختباري", "due_date": "2020-01-01", "priority": "high"},
    )
    assert created.status_code == 201
    assert created.json()["is_overdue"] is True
    overdue = client.get("/api/v1/quality/capa?overdue_only=true", headers=h).json()
    assert any(c["id"] == created.json()["id"] for c in overdue)


# ---- risk score is generated, not trusted from the client -----------------
def test_risk_score_is_computed_by_database(client: TestClient):
    h = _quality_headers(client)
    created = client.post(
        "/api/v1/quality/risks",
        headers=h,
        json={"title": "خطر اختباري", "likelihood": 4, "impact": 5, "category": "medication"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["score"] == 20
    assert body["code"].startswith("RSK-")

    updated = client.patch(
        f"/api/v1/quality/risks/{body['id']}", headers=h, json={"likelihood": 2}
    )
    assert updated.json()["score"] == 10


# ---- audit -> plan -> document -> meeting --------------------------------
def test_audit_plan_document_meeting_flow(client: TestClient):
    h = _quality_headers(client)

    audit = client.post(
        "/api/v1/quality/audits",
        headers=h,
        json={"title": "تدقيق اختباري", "standard_ar": "معيار اختباري", "audit_date": "2026-04-01"},
    )
    assert audit.status_code == 201
    audit_id = audit.json()["id"]
    scored = client.patch(
        f"/api/v1/quality/audits/{audit_id}",
        headers=h,
        json={"status": "completed", "score": 91.5, "findings_ar": "ملاحظات اختبارية."},
    )
    assert scored.json()["score"] == 91.5

    plan = client.post(
        "/api/v1/quality/plans",
        headers=h,
        json={"title": "خطة تحسين اختبارية", "objective_ar": "هدف اختباري", "status": "active"},
    )
    assert plan.status_code == 201
    plan_id = plan.json()["id"]
    action = client.post(
        f"/api/v1/quality/plans/{plan_id}/actions",
        headers=h,
        json={"title": "إجراء اختباري", "due_date": "2026-05-01"},
    )
    assert action.status_code == 201
    detail = client.get(f"/api/v1/quality/plans/{plan_id}", headers=h).json()
    assert len(detail["actions"]) == 1

    doc = client.post(
        "/api/v1/quality/documents",
        headers=h,
        json={"title": "وثيقة اختبارية", "doc_type": "guideline"},
    )
    assert doc.status_code == 201
    approved = client.patch(
        f"/api/v1/quality/documents/{doc.json()['id']}", headers=h, json={"status": "approved"}
    )
    assert approved.json()["approved_at"] is not None

    meeting = client.post(
        "/api/v1/quality/meetings",
        headers=h,
        json={"title": "اجتماع اختباري", "meeting_date": "2026-05-10"},
    )
    assert meeting.status_code == 201
    decision = client.post(
        f"/api/v1/quality/meetings/{meeting.json()['id']}/decisions",
        headers=h,
        json={"decision_ar": "قرار اختباري", "due_date": "2026-06-01"},
    )
    assert decision.status_code == 201
    mdetail = client.get(f"/api/v1/quality/meetings/{meeting.json()['id']}", headers=h).json()
    assert len(mdetail["decisions"]) == 1


# ---- summary reflects stored rows ----------------------------------------
def test_quality_summary_counts(client: TestClient):
    h = _quality_headers(client)
    summary = client.get(f"/api/v1/quality/summary?hospital_id={REP_HOSPITAL}", headers=h)
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["hospital_id"] == REP_HOSPITAL
    assert body["incidents_total"] >= 3
    assert body["capa_total"] >= 3
    assert body["risks_total"] >= 3
    assert body["audits_total"] >= 2
    assert sum(body["incidents_by_severity"].values()) == body["incidents_total"]
    assert sum(body["incidents_by_type"].values()) == body["incidents_total"]


# ---- permissions ----------------------------------------------------------
def test_read_only_user_cannot_write(client: TestClient):
    token = login(client, "rep.reader")
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/quality/incidents", headers=h).status_code == 200
    forbidden = client.post(
        "/api/v1/quality/incidents", headers=h, json={"title": "محاولة كتابة"}
    )
    assert forbidden.status_code == 403


def test_central_admin_must_name_a_hospital(client: TestClient):
    token = login(client, "central.admin")
    h = {"Authorization": f"Bearer {token}"}
    # No hospital_id -> refused with a clear message.
    assert client.post(
        "/api/v1/quality/incidents", headers=h, json={"title": "بلا مستشفى"}
    ).status_code == 400
    ok = client.post(
        "/api/v1/quality/incidents",
        headers=h,
        json={"title": "حادث من الإدارة المركزية", "hospital_id": REP_HOSPITAL},
    )
    assert ok.status_code == 201


# ---- isolation ------------------------------------------------------------
def test_hospital_isolation(client: TestClient):
    # A quality manager of the other hospital sees only their own rows.
    other = login(client, "jum.quality")
    oh = {"Authorization": f"Bearer {other}"}
    incidents = client.get("/api/v1/quality/incidents", headers=oh).json()
    assert all(i["hospital_id"] == JUM_HOSPITAL for i in incidents)
    assert all(i["code"] != "INC-2026-0001" for i in incidents)

    # They cannot read the demo hospital's incident by id (RLS hides it -> 404).
    rep = login(client, "rep.quality")
    rh = {"Authorization": f"Bearer {rep}"}
    demo = client.get("/api/v1/quality/incidents", headers=rh).json()
    demo_id = next(i["id"] for i in demo if i["code"] == "INC-2026-0001")
    assert client.get(f"/api/v1/quality/incidents/{demo_id}", headers=oh).status_code == 404

    # They cannot write into another hospital either.
    assert client.post(
        "/api/v1/quality/incidents",
        headers=oh,
        json={"title": "محاولة كتابة في مستشفى آخر", "hospital_id": REP_HOSPITAL},
    ).status_code == 403


# ---- audit trail ----------------------------------------------------------
def test_quality_writes_are_audited(client: TestClient):
    h = _quality_headers(client)
    created = client.post(
        "/api/v1/quality/incidents", headers=h, json={"title": "حادث للتدقيق"}
    )
    assert created.status_code == 201
    incident_id = created.json()["id"]

    admin = login(client, "central.admin")
    ah = {"Authorization": f"Bearer {admin}"}
    log = client.get("/api/v1/audit-log?entity_type=incident&limit=200", headers=ah)
    assert log.status_code == 200, log.text
    entries = log.json()["entries"]
    assert any(e["entity_id"] == incident_id and e["action"] == "create" for e in entries)


# ---- validation -----------------------------------------------------------
def test_invalid_payloads_are_refused(client: TestClient):
    h = _quality_headers(client)
    # A department that belongs to another hospital must be rejected.
    assert client.post(
        "/api/v1/quality/incidents",
        headers=h,
        json={"title": "قسم خاطئ", "department_id": "01900000-0000-7000-8000-00000000dead"},
    ).status_code == 400
    # Bad enum values are refused by the schema.
    assert client.post(
        "/api/v1/quality/incidents",
        headers=h,
        json={"title": "قيمة غير صحيحة", "severity": "urgent"},
    ).status_code == 422
