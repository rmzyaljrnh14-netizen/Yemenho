"""Seed clearly-labelled DEMO data (never real data).

Creates one central org, one governorate, two hospitals, departments, and users
for each role so the system can be exercised and tested end to end.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.base import AdminSessionLocal
from app.models.core import (
    ConflictLog,
    Department,
    Hospital,
    Indicator,
    IndicatorAssignment,
    IndicatorValue,
    Organization,
    ReportingPeriod,
    Role,
    SyncNode,
    User,
    UserAssignment,
)

# Stable demo ids (readable, obviously demo).
CENTRAL_ID = uuid.UUID("01900000-0000-7000-8000-0000000000c0")
GOV_SANAA_ID = uuid.UUID("01900000-0000-7000-8000-0000000000a1")
GOV_ADEN_ID = uuid.UUID("01900000-0000-7000-8000-0000000000a2")
HOSP_REPUBLICAN_ID = uuid.UUID("01900000-0000-7000-8000-0000000000b1")
HOSP_ALJUMHOURI_ID = uuid.UUID("01900000-0000-7000-8000-0000000000b2")

DEMO_PASSWORD = "Demo@12345"  # demo-only credential, not a secret

DEMO_USERS = [
    ("central.admin", "مدير النظام المركزي (تجريبي)", "central_admin", "central", None),
    ("sanaa.gov", "مسؤول محافظة صنعاء (تجريبي)", "gov_officer", "governorate", GOV_SANAA_ID),
    ("rep.manager", "مدير مستشفى الجمهوري (تجريبي)", "hospital_manager", "hospital", HOSP_REPUBLICAN_ID),
    ("rep.quality", "مدير الجودة - الجمهوري (تجريبي)", "quality_manager", "hospital", HOSP_REPUBLICAN_ID),
    ("rep.reader", "قارئ - الجمهوري (تجريبي)", "read_only", "hospital", HOSP_REPUBLICAN_ID),
    ("jum.quality", "مدير الجودة - الجمهوري الآخر (تجريبي)", "quality_manager", "hospital", HOSP_ALJUMHOURI_ID),
]


def _get_or_create_org(db: Session, **kw) -> Organization:
    existing = db.execute(select(Organization).where(Organization.code == kw.get("code"))).scalar_one_or_none()
    if existing:
        return existing
    org = Organization(**kw)
    db.add(org)
    db.flush()
    return org


def seed(db: Session) -> dict:
    central = _get_or_create_org(db, id=CENTRAL_ID, parent_id=None, level="central",
                                 name_ar="وزارة الصحة العامة والسكان (تجريبي)", code="MOH-DEMO")
    gov_sanaa = _get_or_create_org(db, id=GOV_SANAA_ID, parent_id=central.id, level="governorate",
                                   name_ar="محافظة صنعاء (تجريبي)", code="GOV-SANAA-DEMO")
    gov_aden = _get_or_create_org(db, id=GOV_ADEN_ID, parent_id=central.id, level="governorate",
                                  name_ar="محافظة عدن (تجريبي)", code="GOV-ADEN-DEMO")

    hospitals = {}
    for hid, code, name, gov in [
        (HOSP_REPUBLICAN_ID, "H-SANAA-REP", "هيئة المستشفى الجمهوري التعليمي (تجريبي)", gov_sanaa),
        (HOSP_ALJUMHOURI_ID, "H-SANAA-JUM", "مستشفى الجمهوري الآخر (تجريبي)", gov_sanaa),
    ]:
        existing = db.execute(select(Hospital).where(Hospital.code == code)).scalar_one_or_none()
        if existing is None:
            existing = Hospital(id=hid, name_ar=name, code=code, governorate_id=gov.id, organization_id=gov.id)
            db.add(existing)
            db.flush()
        hospitals[code] = existing

    # Departments for the first hospital.
    dept_specs = [("الطوارئ", "ER"), ("العناية المركزة", "ICU"), ("الجراحة", "SURG"), ("مكافحة العدوى", "IPC")]
    depts = {}
    for name, code in dept_specs:
        existing = db.execute(
            select(Department).where(Department.hospital_id == HOSP_REPUBLICAN_ID, Department.code == code)
        ).scalar_one_or_none()
        if existing is None:
            existing = Department(hospital_id=HOSP_REPUBLICAN_ID, name_ar=name, code=code)
            db.add(existing)
            db.flush()
        depts[code] = existing

    created_users = []
    for username, display, role_code, scope_type, scope_id in DEMO_USERS:
        user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if user is None:
            user = User(username=username, display_name=display, password_hash=hash_password(DEMO_PASSWORD))
            db.add(user)
            db.flush()
            role = db.execute(select(Role).where(Role.code == role_code)).scalar_one()
            db.add(UserAssignment(user_id=user.id, role_id=role.id, scope_type=scope_type, scope_id=scope_id))
            created_users.append(username)

    assigned = _seed_indicator_assignments(db, depts)
    quality = _seed_quality(db, depts)
    sync_demo = _seed_sync_monitor(db)
    db.commit()
    return {
        "demo_password": DEMO_PASSWORD,
        "created_users": created_users,
        "assignments": assigned,
        "quality": quality,
        "sync": sync_demo,
        "note": "بيانات تجريبية واضحة ومنفصلة عن أي بيانات حقيقية.",
    }


# Sync-monitor demo data: one healthy device, one stale device, and one open
# conflict — all clearly labelled demo, so the national monitor is populated for
# a first look and for the browser test. Never real device or user data.
def _seed_sync_monitor(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    specs = [
        # node_id, hospital, name, last_seen
        ("demo-node-rep-01", HOSP_REPUBLICAN_ID, "جهاز الجودة — الجمهوري (تجريبي)", now - timedelta(hours=3)),
        ("demo-node-jum-01", HOSP_ALJUMHOURI_ID, "جهاز الجودة — الجمهوري الآخر (تجريبي)", now - timedelta(days=21)),
    ]
    for node_id, hid, name, last_seen in specs:
        if db.get(SyncNode, node_id) is None:
            db.add(SyncNode(node_id=node_id, hospital_id=hid, name=name, last_seq=25, last_seen_at=last_seen))
    db.flush()

    conflict_id = uuid.UUID("01900000-0000-7000-8000-0000000000d1")
    if db.get(ConflictLog, conflict_id) is None:
        db.add(
            ConflictLog(
                id=conflict_id,
                entity_type="indicator_value",
                entity_id="01900000-0000-7000-8000-0000000000e1",
                node_id="demo-node-rep-01",
                hospital_id=HOSP_REPUBLICAN_ID,
                local_payload={"value": 91.0, "rev": 3},
                server_payload={"value": 88.5, "rev": 4},
                resolution="auto_server",
            )
        )
    db.flush()
    return {"devices": len(specs), "open_conflicts": 1}


# Indicator -> department codes that should own it (empty = whole hospital).
DEMO_ASSIGNMENTS = {
    "PS-INF-RATE": ["IPC"],
    "PS-SSI": ["SURG"],
    "PS-FALLS": ["ICU"],
    "PS-MED-ERR": [],
    "PS-REPORT-RATE": [],
    "QC-READM-30": [],
    "QC-MORT-HOSP": [],
    "QC-AVG-LOS": [],
    "QC-UTIL-BED": [],
    "PX-SAT": [],
    "PX-COMPL": [],
    "IPC-HAND": ["IPC"],
    "IPC-STERIL": ["IPC"],
    "DOC-COMPL": [],
    "MED-RECON": [],
    "SURG-CHECK": ["SURG"],
    "SURG-CANCEL": ["SURG"],
    "ER-TRIAGE": ["ER"],
    "ER-LEAVE": ["ER"],
    "HR-NS-RATIO": ["ICU"],
    "HR-TRAIN": [],
    "CAPA-CLOSE": [],
    "AUDIT-COVER": [],
    "SAFE-TRAIN-N": [],
}


def _seed_indicator_assignments(db: Session, depts: dict) -> int:
    """Assign the demo indicators to the demo hospital (and some departments)."""
    count = 0
    for code, dept_codes in DEMO_ASSIGNMENTS.items():
        indicator = db.execute(select(Indicator).where(Indicator.code == code)).scalar_one_or_none()
        if indicator is None:
            continue
        targets: list[uuid.UUID | None] = [None] + [depts[c].id for c in dept_codes if c in depts]
        for dept_id in targets:
            existing = db.execute(
                select(IndicatorAssignment).where(
                    IndicatorAssignment.indicator_id == indicator.id,
                    IndicatorAssignment.hospital_id == HOSP_REPUBLICAN_ID,
                    IndicatorAssignment.department_id.is_(None)
                    if dept_id is None
                    else IndicatorAssignment.department_id == dept_id,
                    IndicatorAssignment.deleted_at.is_(None),
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(
                    IndicatorAssignment(
                        indicator_id=indicator.id, hospital_id=HOSP_REPUBLICAN_ID, department_id=dept_id
                    )
                )
                count += 1
    db.flush()
    return count


def _d(days: int) -> date:
    """A demo date relative to today (keeps the demo fresh over time)."""
    return date.today() + timedelta(days=days)


def _seed_quality(db: Session, depts: dict) -> dict:
    """Seed clearly-fake quality & patient-safety demo rows.

    Idempotent: if the demo hospital already has incidents, nothing is added.
    """
    from app.models.core import (
        CapaAction,
        ImprovementAction,
        ImprovementPlan,
        Incident,
        IncidentRca,
        IncidentRcaCause,
        QualityAudit,
        QualityDocument,
        QualityMeeting,
        QualityMeetingDecision,
        Risk,
    )

    already = db.execute(
        select(Incident).where(Incident.hospital_id == HOSP_REPUBLICAN_ID)
    ).first()
    if already is not None:
        return {"skipped": "quality demo data already present"}

    er = depts.get("ER")
    icu = depts.get("ICU")
    surg = depts.get("SURG")
    ipc = depts.get("IPC")

    # --- Incidents (clearly fake titles) ---
    incidents = [
        dict(code="INC-2026-0001", title="تأخر إعطاء جرعة دواء (تجريبي)",
             incident_type="medication", severity="moderate", patient_harm="mild",
             department_id=er.id if er else None, status="closed",
             description="مثال توضيحي فقط: تأخر إعطاء جرعة في قسم الطوارئ.",
             immediate_action="تم إعطاء الجرعة ومتابعة المريض (تجريبي)."),
        dict(code="INC-2026-0002", title="سقوط مريض من السرير (تجريبي)",
             incident_type="fall", severity="major", patient_harm="moderate",
             department_id=icu.id if icu else None, status="rca",
             description="مثال توضيحي فقط: سقوط مريض أثناء النقل.",
             immediate_action="تم تقييم المريض وتصوير المنطقة المصابة (تجريبي)."),
        dict(code="INC-2026-0003", title="خطأ في هوية عيّنة مختبر (تجريبي)",
             incident_type="diagnostic", severity="near_miss", patient_harm="none",
             department_id=None, status="under_review",
             description="مثال توضيحي فقط: اكتُشف الخطأ قبل إصدار النتيجة.",
             immediate_action="أُعيد سحب العيّنة بالهوية الصحيحة (تجريبي)."),
    ]
    created_incidents = []
    for spec in incidents:
        row = Incident(hospital_id=HOSP_REPUBLICAN_ID, **spec)
        db.add(row)
        created_incidents.append(row)
    db.flush()

    # --- RCA for the fall incident, with typed causes ---
    fall = created_incidents[1]
    rca = IncidentRca(
        incident_id=fall.id, hospital_id=HOSP_REPUBLICAN_ID, status="in_progress",
        method="five_whys", team_ar="فريق الجودة (تجريبي)",
        timeline_ar="١) نقل المريض ٢) غياب حواجز السرير ٣) السقوط (تجريبي).",
        findings_ar="مثال توضيحي: عدم تفعيل حواجز السرير أثناء النقل.",
    )
    db.add(rca)
    db.flush()
    for spec in [
        dict(category="process", description_ar="لا توجد قائمة تحقق لنقل المرضى المعرّضين للسقوط.", is_root_cause=True),
        dict(category="environment", description_ar="حواجز السرير لم تُفعّل أثناء النقل.", is_root_cause=False),
        dict(category="training", description_ar="الحاجة إلى تدريب متكرر على بروتوكول منع السقوط.", is_root_cause=False),
    ]:
        db.add(IncidentRcaCause(rca_id=rca.id, **spec))

    # --- CAPA linked to the RCA and to the audit ---
    capas = [
        dict(kind="corrective", title="اعتماد قائمة تحقق لنقل المرضى (تجريبي)",
             rca_id=rca.id, incident_id=fall.id, priority="high", status="in_progress",
             due_date=_d(40), owner_name_ar="مسؤول الجودة (تجريبي)",
             description_ar="مثال توضيحي: قائمة إلزامية قبل نقل أي مريض معرّض للسقوط."),
        dict(kind="preventive", title="تدريب الكوادر على بروتوكول منع السقوط (تجريبي)",
             incident_id=None, rca_id=None, priority="medium", status="open",
             due_date=_d(-20), owner_name_ar="مسؤول التدريب (تجريبي)",
             description_ar="مثال توضيحي: جلسات تدريب ربعية."),
        dict(kind="corrective", title="مراجعة إجراءات هوية العيّنات (تجريبي)",
             incident_id=created_incidents[2].id, priority="high", status="open",
             due_date=_d(-45), owner_name_ar="مسؤول المختبر (تجريبي)",
             description_ar="مثال توضيحي: تحقق مزدوج قبل سحب العيّنة."),
    ]
    for spec in capas:
        db.add(CapaAction(hospital_id=HOSP_REPUBLICAN_ID, **spec))

    # --- Risk register (score is computed by the database) ---
    for spec in [
        dict(code="RSK-2026-0001", title="خطر العدوى المرتبطة بالقسطرة (تجريبي)",
             category="infection", likelihood=3, impact=5, status="open",
             mitigation_ar="مثال توضيحي: حزمة الوقاية من العدوى المرتبطة بالقسطرة.",
             owner_name_ar="مسؤول مكافحة العدوى (تجريبي)", department_id=ipc.id if ipc else None),
        dict(code="RSK-2026-0002", title="نقص الكوادر في العناية المركزة (تجريبي)",
             category="staffing", likelihood=4, impact=4, status="mitigated",
             mitigation_ar="مثال توضيحي: خطة تغطية ومناوبات.",
             owner_name_ar="مدير المستشفى (تجريبي)", department_id=icu.id if icu else None),
        dict(code="RSK-2026-0003", title="أعطال أجهزة المراقبة (تجريبي)",
             category="equipment", likelihood=2, impact=3, status="open",
             mitigation_ar="مثال توضيحي: صيانة دورية وسجل أعطال.",
             owner_name_ar="مسؤول الصيانة (تجريبي)", department_id=None),
    ]:
        db.add(Risk(hospital_id=HOSP_REPUBLICAN_ID, **spec))

    # --- Internal audits ---
    audits = [
        dict(code="AUD-2026-0001", title="تدقيق الالتزام بنظافة اليدين (تجريبي)",
             standard_ar="معيار السلامة الوطنية (تجريبي)", status="completed",
             score=88, audit_date=_d(-60), department_id=ipc.id if ipc else None,
             auditor_name_ar="المدقق الداخلي (تجريبي)",
             findings_ar="مثال توضيحي: التزام جيد مع حاجة لتعزيز في المناوبات الليلية."),
        dict(code="AUD-2026-0002", title="تدقيق التجهيز الجراحي (تجريبي)",
             standard_ar="معيار السلامة الوطنية (تجريبي)", status="planned",
             audit_date=_d(15), department_id=surg.id if surg else None,
             auditor_name_ar="المدقق الداخلي (تجريبي)"),
    ]
    for spec in audits:
        db.add(QualityAudit(hospital_id=HOSP_REPUBLICAN_ID, **spec))

    # --- Improvement plan with tracked actions ---
    plan = ImprovementPlan(
        hospital_id=HOSP_REPUBLICAN_ID, code="IMP-2026-0001",
        title="خطة خفض معدل السقوط (تجريبي)", status="active",
        objective_ar="مثال توضيحي: خفض معدل سقوط المرضى بنسبة 30% خلال ستة أشهر.",
        baseline_ar="القيمة الأساسية: 3 حالات لكل 1000 يوم مريض (تجريبي).",
        target_ar="القيمة المستهدفة: 2 لكل 1000 يوم مريض (تجريبي).",
        owner_name_ar="مدير الجودة (تجريبي)",
        start_date=_d(-90), due_date=_d(120),
        department_id=icu.id if icu else None,
    )
    db.add(plan)
    db.flush()
    for spec in [
        dict(title="تعميم قائمة تحقق النقل (تجريبي)", status="in_progress",
             owner_name_ar="مسؤول الجودة (تجريبي)", due_date=_d(30)),
        dict(title="تدريب الكوادر على منع السقوط (تجريبي)", status="open",
             owner_name_ar="مسؤول التدريب (تجريبي)", due_date=_d(45)),
    ]:
        db.add(ImprovementAction(plan_id=plan.id, **spec))

    # --- Documents & policies ---
    for spec in [
        dict(code="DOC-2026-0001", title="سياسة سلامة المرضى (تجريبي)",
             doc_type="policy", version="1.0", status="approved",
             summary_ar="مثال توضيحي: سياسة عامة لسلامة المرضى.",
             owner_name_ar="مدير الجودة (تجريبي)",
             effective_date=_d(-90), review_date=_d(300)),
        dict(code="DOC-2026-0002", title="إجراء منع السقوط (تجريبي)",
             doc_type="procedure", version="1.1", status="under_review",
             summary_ar="مثال توضيحي: خطوات منع سقوط المرضى.",
             owner_name_ar="مسؤول الجودة (تجريبي)"),
    ]:
        db.add(QualityDocument(hospital_id=HOSP_REPUBLICAN_ID, **spec))

    # --- Quality meeting with decisions ---
    meeting = QualityMeeting(
        hospital_id=HOSP_REPUBLICAN_ID, title="اجتماع لجنة الجودة الشهري (تجريبي)",
        meeting_date=_d(-30), location_ar="قاعة الاجتماعات (تجريبي)",
        chair_name_ar="مدير المستشفى (تجريبي)",
        attendees_ar="لجنة الجودة والسلامة (تجريبي)",
        agenda_ar="مثال توضيحي: مراجعة الحوادث وخطط التحسين.",
        minutes_ar="مثال توضيحي: نوقشت نتائج تدقيق نظافة اليدين.",
        status="held",
    )
    db.add(meeting)
    db.flush()
    for spec in [
        dict(decision_ar="اعتماد قائمة تحقق النقل قبل نهاية الربع (تجريبي)",
             owner_name_ar="مسؤول الجودة (تجريبي)", due_date=_d(40)),
        dict(decision_ar="تعزيز التدريب على منع السقوط (تجريبي)",
             owner_name_ar="مسؤول التدريب (تجريبي)", due_date=_d(30)),
    ]:
        db.add(QualityMeetingDecision(meeting_id=meeting.id, **spec))

    db.flush()
    return {
        "incidents": len(created_incidents),
        "capas": len(capas),
        "risks": 3,
        "audits": len(audits),
        "plans": 1,
        "documents": 2,
        "meetings": 1,
    }


def main() -> None:
    db = AdminSessionLocal()
    try:
        print(seed(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()