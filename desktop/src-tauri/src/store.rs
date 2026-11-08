// Offline store for the desktop app (v0.6).
//
// The app must keep working with no internet: every edit is written to a local
// SQLite database first, then queued in an outbox. When the connection returns
// the queue is pushed (each op carries a unique op_id so a retry never
// duplicates) and the server's changes are pulled back with a cursor.
//
// This module owns the durable local state only. Network calls are made by the
// web UI (which already holds the session token), keeping credential handling
// in one place.

use std::path::PathBuf;
use std::sync::Mutex;

use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

const SCHEMA: &str = r#"
CREATE TABLE IF NOT EXISTS local_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS local_period (
    id          TEXT PRIMARY KEY,
    hospital_id TEXT,
    period_type TEXT NOT NULL,
    year        INTEGER NOT NULL,
    month       INTEGER,
    quarter     INTEGER,
    status      TEXT NOT NULL DEFAULT 'draft',
    rev         INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT,
    synced      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS local_value (
    id            TEXT PRIMARY KEY,
    period_id     TEXT NOT NULL,
    indicator_id  TEXT NOT NULL,
    department_id TEXT,
    numerator     REAL,
    denominator   REAL,
    value         REAL,
    value_type    TEXT NOT NULL DEFAULT 'computed',
    assessment    TEXT,
    assessment_ar TEXT,
    note          TEXT,
    rev           INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT,
    synced        INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS local_incident (
    id               TEXT PRIMARY KEY,
    hospital_id      TEXT,
    department_id    TEXT,
    code             TEXT,
    title            TEXT NOT NULL,
    description      TEXT,
    incident_type    TEXT NOT NULL DEFAULT 'other',
    severity         TEXT NOT NULL DEFAULT 'moderate',
    patient_harm     TEXT NOT NULL DEFAULT 'none',
    occurred_at      TEXT,
    reported_at      TEXT,
    is_anonymous     INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'reported',
    immediate_action TEXT,
    rev              INTEGER NOT NULL DEFAULT 0,
    updated_at       TEXT,
    synced           INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_local_incident_status ON local_incident(status, updated_at);
CREATE TABLE IF NOT EXISTS local_capa (
    id                 TEXT PRIMARY KEY,
    hospital_id        TEXT,
    department_id      TEXT,
    incident_id        TEXT,
    kind               TEXT NOT NULL DEFAULT 'corrective',
    title              TEXT NOT NULL,
    description_ar     TEXT,
    owner_name_ar      TEXT,
    due_date           TEXT,
    priority           TEXT NOT NULL DEFAULT 'medium',
    status             TEXT NOT NULL DEFAULT 'open',
    completion_note_ar TEXT,
    rev                INTEGER NOT NULL DEFAULT 0,
    updated_at         TEXT,
    synced             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_local_capa_status ON local_capa(status, updated_at);
CREATE TABLE IF NOT EXISTS local_risk (
    id             TEXT PRIMARY KEY,
    hospital_id    TEXT,
    department_id  TEXT,
    code           TEXT,
    title          TEXT NOT NULL,
    description_ar TEXT,
    category       TEXT NOT NULL DEFAULT 'clinical',
    likelihood     INTEGER NOT NULL DEFAULT 3,
    impact         INTEGER NOT NULL DEFAULT 3,
    score          INTEGER,
    mitigation_ar  TEXT,
    owner_name_ar  TEXT,
    review_date    TEXT,
    status         TEXT NOT NULL DEFAULT 'open',
    rev            INTEGER NOT NULL DEFAULT 0,
    updated_at     TEXT,
    synced         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_local_risk_status ON local_risk(status, updated_at);
CREATE TABLE IF NOT EXISTS local_audit (
    id              TEXT PRIMARY KEY,
    hospital_id     TEXT,
    department_id   TEXT,
    code            TEXT,
    title           TEXT NOT NULL,
    standard_ar     TEXT,
    scope_ar        TEXT,
    auditor_name_ar TEXT,
    audit_date      TEXT,
    status          TEXT NOT NULL DEFAULT 'planned',
    score           REAL,
    findings_ar     TEXT,
    rev             INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT,
    synced          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_local_audit_status ON local_audit(status, updated_at);
CREATE TABLE IF NOT EXISTS local_plan (
    id            TEXT PRIMARY KEY,
    hospital_id   TEXT,
    department_id TEXT,
    code          TEXT,
    title         TEXT NOT NULL,
    objective_ar  TEXT,
    baseline_ar   TEXT,
    target_ar     TEXT,
    owner_name_ar TEXT,
    start_date    TEXT,
    due_date      TEXT,
    status        TEXT NOT NULL DEFAULT 'draft',
    rev           INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT,
    synced        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_local_plan_status ON local_plan(status, updated_at);
CREATE TABLE IF NOT EXISTS local_plan_action (
    id            TEXT PRIMARY KEY,
    plan_id       TEXT NOT NULL,
    title         TEXT NOT NULL,
    owner_name_ar TEXT,
    due_date      TEXT,
    status        TEXT NOT NULL DEFAULT 'open',
    note_ar       TEXT,
    rev           INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT,
    synced        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_local_plan_action_plan ON local_plan_action(plan_id, updated_at);
CREATE TABLE IF NOT EXISTS outbox (
    id          TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    op          TEXT NOT NULL DEFAULT 'upsert',
    base_rev    INTEGER NOT NULL DEFAULT 0,
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    state       TEXT NOT NULL DEFAULT 'pending',
    last_error  TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_state ON outbox(state, created_at);
CREATE TABLE IF NOT EXISTS library (
    id      TEXT PRIMARY KEY,
    kind    TEXT NOT NULL DEFAULT 'indicator',
    code    TEXT,
    name_ar TEXT,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conflict (
    id             TEXT PRIMARY KEY,
    entity_type    TEXT NOT NULL,
    entity_id      TEXT NOT NULL,
    local_payload  TEXT,
    server_payload TEXT,
    resolution     TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
"#;

pub struct Store {
    conn: Mutex<Connection>,
    pub db_path: PathBuf,
}

#[derive(Serialize)]
pub struct LocalStatus {
    pub node_id: String,
    pub hospital_id: Option<String>,
    pub cursor: i64,
    pub pending_count: i64,
    pub failed_count: i64,
    pub conflict_count: i64,
    pub last_sync_at: Option<String>,
    pub db_path: String,
}

#[derive(Serialize)]
pub struct PendingOp {
    pub op_id: String,
    pub entity_type: String,
    pub entity_id: String,
    pub op: String,
    pub base_rev: i64,
    pub payload: Value,
    pub attempts: i64,
    pub state: String,
    pub last_error: Option<String>,
}

impl Store {
    pub fn open(db_path: PathBuf) -> Result<Self, String> {
        let conn = Connection::open(&db_path).map_err(|e| format!("open db: {e}"))?;
        conn.execute_batch(SCHEMA).map_err(|e| format!("schema: {e}"))?;
        let store = Store {
            conn: Mutex::new(conn),
            db_path,
        };
        store.ensure_node_id()?;
        Ok(store)
    }

    fn lock(&self) -> Result<std::sync::MutexGuard<'_, Connection>, String> {
        self.conn
            .lock()
            .map_err(|_| "local database lock poisoned".to_string())
    }

    fn meta_get(conn: &Connection, key: &str) -> Result<Option<String>, String> {
        conn.query_row("SELECT value FROM local_meta WHERE key = ?1", params![key], |r| {
            r.get::<_, String>(0)
        })
        .optional()
        .map_err(|e| format!("meta get: {e}"))
    }

    fn meta_set(conn: &Connection, key: &str, value: &str) -> Result<(), String> {
        conn.execute(
            "INSERT INTO local_meta(key, value) VALUES(?1, ?2)
             ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            params![key, value],
        )
        .map_err(|e| format!("meta set: {e}"))?;
        Ok(())
    }

    fn ensure_node_id(&self) -> Result<(), String> {
        let conn = self.lock()?;
        if Self::meta_get(&conn, "node_id")?.is_none() {
            let node = format!("node-{}", uuid::Uuid::new_v4());
            Self::meta_set(&conn, "node_id", &node)?;
        }
        if Self::meta_get(&conn, "cursor")?.is_none() {
            Self::meta_set(&conn, "cursor", "0")?;
        }
        Ok(())
    }

    pub fn status(&self) -> Result<LocalStatus, String> {
        let conn = self.lock()?;
        let node_id = Self::meta_get(&conn, "node_id")?.unwrap_or_default();
        let hospital_id = Self::meta_get(&conn, "hospital_id")?;
        let cursor = Self::meta_get(&conn, "cursor")?
            .and_then(|v| v.parse::<i64>().ok())
            .unwrap_or(0);
        let last_sync_at = Self::meta_get(&conn, "last_sync_at")?;
        let pending_count: i64 = conn
            .query_row("SELECT COUNT(*) FROM outbox WHERE state = 'pending'", [], |r| r.get(0))
            .map_err(|e| format!("count pending: {e}"))?;
        let failed_count: i64 = conn
            .query_row("SELECT COUNT(*) FROM outbox WHERE state = 'failed'", [], |r| r.get(0))
            .map_err(|e| format!("count failed: {e}"))?;
        let conflict_count: i64 = conn
            .query_row("SELECT COUNT(*) FROM conflict", [], |r| r.get(0))
            .map_err(|e| format!("count conflict: {e}"))?;
        Ok(LocalStatus {
            node_id,
            hospital_id,
            cursor,
            pending_count,
            failed_count,
            conflict_count,
            last_sync_at,
            db_path: self.db_path.to_string_lossy().to_string(),
        })
    }

    pub fn set_hospital(&self, hospital_id: &str) -> Result<(), String> {
        let conn = self.lock()?;
        Self::meta_set(&conn, "hospital_id", hospital_id)
    }

    pub fn set_cursor(&self, seq: i64) -> Result<(), String> {
        let conn = self.lock()?;
        Self::meta_set(&conn, "cursor", &seq.to_string())
    }

    pub fn mark_synced_now(&self, at: &str) -> Result<(), String> {
        let conn = self.lock()?;
        Self::meta_set(&conn, "last_sync_at", at)
    }

    /// Save an indicator value locally and queue it for sync.
    #[allow(clippy::too_many_arguments)]
    pub fn save_value(
        &self,
        value_id: &str,
        period_id: &str,
        indicator_id: &str,
        department_id: Option<&str>,
        numerator: Option<f64>,
        denominator: Option<f64>,
        entered_value: Option<f64>,
        computation: &str,
        multiplier: Option<f64>,
        direction: &str,
        target_value: Option<f64>,
        acceptable_min: Option<f64>,
        acceptable_max: Option<f64>,
        note: Option<&str>,
        at: &str,
    ) -> Result<Value, String> {
        let (value, value_type) =
            compute_value(computation, numerator, denominator, multiplier, entered_value);
        let (status, label) = assess(direction, value, target_value, acceptable_min, acceptable_max);
        let payload = json!({
            "id": value_id,
            "period_id": period_id,
            "indicator_id": indicator_id,
            "department_id": department_id,
            "numerator": numerator,
            "denominator": denominator,
            "entered_value": entered_value,
            "value": value,
            "value_type": value_type,
            "note": note,
        });
        let mut conn = self.lock()?;
        let tx = conn.transaction().map_err(|e| format!("tx: {e}"))?;
        let base_rev: i64 = tx
            .query_row("SELECT rev FROM local_value WHERE id = ?1", params![value_id], |r| r.get(0))
            .optional()
            .map_err(|e| format!("rev read: {e}"))?
            .unwrap_or(0);
        tx.execute(
            "INSERT INTO local_value(id, period_id, indicator_id, department_id, numerator, denominator,
                                     value, value_type, assessment, assessment_ar, note, rev, updated_at, synced)
             VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,0)
             ON CONFLICT(id) DO UPDATE SET
                numerator = excluded.numerator, denominator = excluded.denominator,
                value = excluded.value, value_type = excluded.value_type,
                assessment = excluded.assessment, assessment_ar = excluded.assessment_ar,
                note = excluded.note, updated_at = excluded.updated_at, synced = 0",
            params![
                value_id, period_id, indicator_id, department_id, numerator, denominator,
                value, value_type, status, label, note, base_rev + 1, at
            ],
        )
        .map_err(|e| format!("save value: {e}"))?;
        let op_id = format!("op-{}", uuid::Uuid::new_v4());
        tx.execute(
            "INSERT INTO outbox(id, entity_type, entity_id, op, base_rev, payload, created_at, state)
             VALUES(?1, 'indicator_value', ?2, 'upsert', ?3, ?4, ?5, 'pending')",
            params![op_id, value_id, base_rev, payload.to_string(), at],
        )
        .map_err(|e| format!("enqueue: {e}"))?;
        tx.commit().map_err(|e| format!("commit: {e}"))?;
        Ok(json!({
            "value_id": value_id,
            "op_id": op_id,
            "value": value,
            "value_type": value_type,
            "assessment": status,
            "assessment_ar": label,
        }))
    }

    /// Create a reporting period locally and queue it for sync.
    #[allow(clippy::too_many_arguments)]
    pub fn create_period(
        &self,
        period_id: &str,
        hospital_id: &str,
        period_type: &str,
        year: i64,
        month: Option<i64>,
        quarter: Option<i64>,
        at: &str,
    ) -> Result<Value, String> {
        let payload = json!({
            "id": period_id,
            "hospital_id": hospital_id,
            "period_type": period_type,
            "year": year,
            "month": month,
            "quarter": quarter,
        });
        let mut conn = self.lock()?;
        let tx = conn.transaction().map_err(|e| format!("tx: {e}"))?;
        tx.execute(
            "INSERT INTO local_period(id, hospital_id, period_type, year, month, quarter, status, rev, updated_at, synced)
             VALUES(?1,?2,?3,?4,?5,?6,'draft',0,?7,0)
             ON CONFLICT(id) DO NOTHING",
            params![period_id, hospital_id, period_type, year, month, quarter, at],
        )
        .map_err(|e| format!("save period: {e}"))?;
        let op_id = format!("op-{}", uuid::Uuid::new_v4());
        tx.execute(
            "INSERT INTO outbox(id, entity_type, entity_id, op, base_rev, payload, created_at, state)
             VALUES(?1, 'reporting_period', ?2, 'upsert', 0, ?3, ?4, 'pending')",
            params![op_id, period_id, payload.to_string(), at],
        )
        .map_err(|e| format!("enqueue period: {e}"))?;
        tx.commit().map_err(|e| format!("commit: {e}"))?;
        Ok(json!({ "period_id": period_id, "op_id": op_id }))
    }

    pub fn list_periods(&self, hospital_id: Option<&str>) -> Result<Vec<Value>, String> {
        let conn = self.lock()?;
        let (sql, filter): (&str, Option<&str>) = match hospital_id {
            Some(_) => (
                "SELECT id, hospital_id, period_type, year, month, quarter, status, rev, synced
                 FROM local_period WHERE hospital_id = ?1 ORDER BY year DESC, month DESC",
                hospital_id,
            ),
            None => (
                "SELECT id, hospital_id, period_type, year, month, quarter, status, rev, synced
                 FROM local_period ORDER BY year DESC, month DESC",
                None,
            ),
        };
        let mut stmt = conn.prepare(sql).map_err(|e| format!("prepare: {e}"))?;
        let map_row = |r: &rusqlite::Row<'_>| {
            Ok(json!({
                "id": r.get::<_, String>(0)?,
                "hospital_id": r.get::<_, Option<String>>(1)?,
                "period_type": r.get::<_, String>(2)?,
                "year": r.get::<_, i64>(3)?,
                "month": r.get::<_, Option<i64>>(4)?,
                "quarter": r.get::<_, Option<i64>>(5)?,
                "status": r.get::<_, String>(6)?,
                "rev": r.get::<_, i64>(7)?,
                "synced": r.get::<_, i64>(8)? != 0,
            }))
        };
        let rows = match filter {
            Some(f) => stmt.query_map(params![f], map_row),
            None => stmt.query_map([], map_row),
        }
        .map_err(|e| format!("query: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>().map_err(|e| format!("rows: {e}"))
    }

    /// Cache a list of reference records (hospitals, departments) so the entry
    /// form still works offline. Indicators use `cache_library`.
    pub fn cache_refs(&self, kind: &str, items: &[Value]) -> Result<usize, String> {
        let mut conn = self.lock()?;
        let tx = conn.transaction().map_err(|e| format!("tx: {e}"))?;
        let mut count = 0usize;
        for d in items {
            let id = d.get("id").and_then(|v| v.as_str()).unwrap_or("");
            if id.is_empty() {
                continue;
            }
            let code = d.get("code").and_then(|v| v.as_str()).unwrap_or("");
            let name_ar = d.get("name_ar").and_then(|v| v.as_str()).unwrap_or("");
            tx.execute(
                "INSERT INTO library(id, kind, code, name_ar, payload) VALUES(?1, ?2, ?3, ?4, ?5)
                 ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, code=excluded.code,
                    name_ar=excluded.name_ar, payload=excluded.payload",
                params![id, kind, code, name_ar, d.to_string()],
            )
            .map_err(|e| format!("cache {kind}: {e}"))?;
            count += 1;
        }
        tx.commit().map_err(|e| format!("commit cache {kind}: {e}"))?;
        Ok(count)
    }

    pub fn list_refs(&self, kind: &str) -> Result<Vec<Value>, String> {
        let conn = self.lock()?;
        let mut stmt = conn
            .prepare("SELECT payload FROM library WHERE kind = ?1 ORDER BY name_ar")
            .map_err(|e| format!("prepare: {e}"))?;
        let rows = stmt
            .query_map(params![kind], |r| {
                let payload: String = r.get(0)?;
                Ok(serde_json::from_str::<Value>(&payload).unwrap_or(Value::Null))
            })
            .map_err(|e| format!("query: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>().map_err(|e| format!("rows: {e}"))
    }

    pub fn cache_departments(&self, departments: &[Value]) -> Result<usize, String> {
        self.cache_refs("department", departments)
    }

    pub fn list_departments(&self) -> Result<Vec<Value>, String> {
        self.list_refs("department")
    }

    pub fn cache_hospitals(&self, hospitals: &[Value]) -> Result<usize, String> {
        self.cache_refs("hospital", hospitals)
    }

    pub fn list_hospitals(&self) -> Result<Vec<Value>, String> {
        self.list_refs("hospital")
    }

    pub fn cache_assignments(&self, assignments: &[Value]) -> Result<usize, String> {
        self.cache_refs("assignment", assignments)
    }

    pub fn list_assignments(&self) -> Result<Vec<Value>, String> {
        self.list_refs("assignment")
    }

    pub fn list_values(&self, period_id: &str) -> Result<Vec<Value>, String> {
        let conn = self.lock()?;
        let mut stmt = conn
            .prepare(
                "SELECT id, indicator_id, department_id, numerator, denominator, value, value_type,
                        assessment, assessment_ar, note, synced
                 FROM local_value WHERE period_id = ?1 ORDER BY updated_at DESC",
            )
            .map_err(|e| format!("prepare: {e}"))?;
        let rows = stmt
            .query_map(params![period_id], |r| {
                Ok(json!({
                    "id": r.get::<_, String>(0)?,
                    "indicator_id": r.get::<_, String>(1)?,
                    "department_id": r.get::<_, Option<String>>(2)?,
                    "numerator": r.get::<_, Option<f64>>(3)?,
                    "denominator": r.get::<_, Option<f64>>(4)?,
                    "value": r.get::<_, Option<f64>>(5)?,
                    "value_type": r.get::<_, String>(6)?,
                    "assessment": r.get::<_, Option<String>>(7)?,
                    "assessment_ar": r.get::<_, Option<String>>(8)?,
                    "note": r.get::<_, Option<String>>(9)?,
                    "synced": r.get::<_, i64>(10)? != 0,
                }))
            })
            .map_err(|e| format!("query: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>().map_err(|e| format!("rows: {e}"))
    }

    /// Save a patient-safety incident locally and queue it for sync.
    ///
    /// The server owns the human code and the workflow status, so a local row
    /// starts with no code and status `reported`; both are filled in when the
    /// push is acknowledged or the row is pulled back.
    #[allow(clippy::too_many_arguments)]
    pub fn save_incident(
        &self,
        incident_id: &str,
        hospital_id: &str,
        department_id: Option<&str>,
        title: &str,
        description: Option<&str>,
        incident_type: &str,
        severity: &str,
        patient_harm: &str,
        occurred_at: Option<&str>,
        is_anonymous: bool,
        immediate_action: Option<&str>,
        at: &str,
    ) -> Result<Value, String> {
        let payload = json!({
            "id": incident_id,
            "department_id": department_id,
            "title": title,
            "description": description,
            "incident_type": incident_type,
            "severity": severity,
            "patient_harm": patient_harm,
            "occurred_at": occurred_at,
            "is_anonymous": is_anonymous,
            "immediate_action": immediate_action,
        });
        let mut conn = self.lock()?;
        let tx = conn.transaction().map_err(|e| format!("tx: {e}"))?;
        let base_rev: i64 = tx
            .query_row("SELECT rev FROM local_incident WHERE id = ?1", params![incident_id], |r| r.get(0))
            .optional()
            .map_err(|e| format!("rev read: {e}"))?
            .unwrap_or(0);
        tx.execute(
            "INSERT INTO local_incident(id, hospital_id, department_id, title, description, incident_type,
                                        severity, patient_harm, occurred_at, reported_at, is_anonymous,
                                        status, immediate_action, rev, updated_at, synced)
             VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,'reported',?12,?13,?14,0)
             ON CONFLICT(id) DO UPDATE SET
                department_id = excluded.department_id, title = excluded.title,
                description = excluded.description, incident_type = excluded.incident_type,
                severity = excluded.severity, patient_harm = excluded.patient_harm,
                occurred_at = excluded.occurred_at, is_anonymous = excluded.is_anonymous,
                immediate_action = excluded.immediate_action, updated_at = excluded.updated_at,
                synced = 0",
            params![
                incident_id, hospital_id, department_id, title, description, incident_type,
                severity, patient_harm, occurred_at, at, is_anonymous as i64,
                immediate_action, base_rev + 1, at
            ],
        )
        .map_err(|e| format!("save incident: {e}"))?;
        let op_id = format!("op-{}", uuid::Uuid::new_v4());
        tx.execute(
            "INSERT INTO outbox(id, entity_type, entity_id, op, base_rev, payload, created_at, state)
             VALUES(?1, 'incident', ?2, 'upsert', ?3, ?4, ?5, 'pending')",
            params![op_id, incident_id, base_rev, payload.to_string(), at],
        )
        .map_err(|e| format!("enqueue incident: {e}"))?;
        tx.commit().map_err(|e| format!("commit: {e}"))?;
        Ok(json!({ "incident_id": incident_id, "op_id": op_id }))
    }

    pub fn list_incidents(&self, hospital_id: Option<&str>) -> Result<Vec<Value>, String> {
        let conn = self.lock()?;
        let (sql, filter): (&str, Option<&str>) = match hospital_id {
            Some(_) => (
                "SELECT id, hospital_id, department_id, code, title, description, incident_type,
                        severity, patient_harm, occurred_at, reported_at, is_anonymous, status,
                        immediate_action, rev, synced
                 FROM local_incident WHERE hospital_id = ?1 ORDER BY COALESCE(reported_at, updated_at) DESC",
                hospital_id,
            ),
            None => (
                "SELECT id, hospital_id, department_id, code, title, description, incident_type,
                        severity, patient_harm, occurred_at, reported_at, is_anonymous, status,
                        immediate_action, rev, synced
                 FROM local_incident ORDER BY COALESCE(reported_at, updated_at) DESC",
                None,
            ),
        };
        let mut stmt = conn.prepare(sql).map_err(|e| format!("prepare: {e}"))?;
        let map_row = |r: &rusqlite::Row<'_>| {
            Ok(json!({
                "id": r.get::<_, String>(0)?,
                "hospital_id": r.get::<_, Option<String>>(1)?,
                "department_id": r.get::<_, Option<String>>(2)?,
                "code": r.get::<_, Option<String>>(3)?,
                "title": r.get::<_, String>(4)?,
                "description": r.get::<_, Option<String>>(5)?,
                "incident_type": r.get::<_, String>(6)?,
                "severity": r.get::<_, String>(7)?,
                "patient_harm": r.get::<_, String>(8)?,
                "occurred_at": r.get::<_, Option<String>>(9)?,
                "reported_at": r.get::<_, Option<String>>(10)?,
                "is_anonymous": r.get::<_, i64>(11)? != 0,
                "status": r.get::<_, String>(12)?,
                "immediate_action": r.get::<_, Option<String>>(13)?,
                "rev": r.get::<_, i64>(14)?,
                "synced": r.get::<_, i64>(15)? != 0,
            }))
        };
        let rows = match filter {
            Some(f) => stmt.query_map(params![f], map_row),
            None => stmt.query_map([], map_row),
        }
        .map_err(|e| format!("query: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>().map_err(|e| format!("rows: {e}"))
    }

    #[allow(clippy::too_many_arguments)]
    pub fn save_capa(
        &self,
        capa_id: &str,
        hospital_id: &str,
        department_id: Option<&str>,
        incident_id: Option<&str>,
        kind: &str,
        title: &str,
        description_ar: Option<&str>,
        owner_name_ar: Option<&str>,
        due_date: Option<&str>,
        priority: &str,
        at: &str,
    ) -> Result<Value, String> {
        let payload = json!({
            "id": capa_id,
            "department_id": department_id,
            "incident_id": incident_id,
            "kind": kind,
            "title": title,
            "description_ar": description_ar,
            "owner_name_ar": owner_name_ar,
            "due_date": due_date,
            "priority": priority,
            "status": "open",
        });
        let mut conn = self.lock()?;
        let tx = conn.transaction().map_err(|e| format!("tx: {e}"))?;
        let base_rev: i64 = tx
            .query_row("SELECT rev FROM local_capa WHERE id = ?1", params![capa_id], |r| r.get(0))
            .optional()
            .map_err(|e| format!("rev read: {e}"))?
            .unwrap_or(0);
        tx.execute(
            "INSERT INTO local_capa(id, hospital_id, department_id, incident_id, kind, title,
                                    description_ar, owner_name_ar, due_date, priority, status,
                                    rev, updated_at, synced)
             VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,'open',?11,?12,0)
             ON CONFLICT(id) DO UPDATE SET
                department_id = excluded.department_id, incident_id = excluded.incident_id,
                kind = excluded.kind, title = excluded.title,
                description_ar = excluded.description_ar, owner_name_ar = excluded.owner_name_ar,
                due_date = excluded.due_date, priority = excluded.priority,
                updated_at = excluded.updated_at, synced = 0",
            params![
                capa_id, hospital_id, department_id, incident_id, kind, title,
                description_ar, owner_name_ar, due_date, priority, base_rev + 1, at
            ],
        )
        .map_err(|e| format!("save capa: {e}"))?;
        let op_id = format!("op-{}", uuid::Uuid::new_v4());
        tx.execute(
            "INSERT INTO outbox(id, entity_type, entity_id, op, base_rev, payload, created_at, state)
             VALUES(?1, 'capa_action', ?2, 'upsert', ?3, ?4, ?5, 'pending')",
            params![op_id, capa_id, base_rev, payload.to_string(), at],
        )
        .map_err(|e| format!("enqueue capa: {e}"))?;
        tx.commit().map_err(|e| format!("commit: {e}"))?;
        Ok(json!({ "capa_id": capa_id, "op_id": op_id }))
    }

    pub fn list_capa(&self, hospital_id: Option<&str>) -> Result<Vec<Value>, String> {
        let conn = self.lock()?;
        let (sql, filter): (&str, Option<&str>) = match hospital_id {
            Some(_) => (
                "SELECT id, hospital_id, department_id, incident_id, kind, title, description_ar,
                        owner_name_ar, due_date, priority, status, completion_note_ar, rev, synced
                 FROM local_capa WHERE hospital_id = ?1 ORDER BY due_date IS NULL, due_date",
                hospital_id,
            ),
            None => (
                "SELECT id, hospital_id, department_id, incident_id, kind, title, description_ar,
                        owner_name_ar, due_date, priority, status, completion_note_ar, rev, synced
                 FROM local_capa ORDER BY due_date IS NULL, due_date",
                None,
            ),
        };
        let mut stmt = conn.prepare(sql).map_err(|e| format!("prepare: {e}"))?;
        let map_row = |r: &rusqlite::Row<'_>| {
            Ok(json!({
                "id": r.get::<_, String>(0)?,
                "hospital_id": r.get::<_, Option<String>>(1)?,
                "department_id": r.get::<_, Option<String>>(2)?,
                "incident_id": r.get::<_, Option<String>>(3)?,
                "kind": r.get::<_, String>(4)?,
                "title": r.get::<_, String>(5)?,
                "description_ar": r.get::<_, Option<String>>(6)?,
                "owner_name_ar": r.get::<_, Option<String>>(7)?,
                "due_date": r.get::<_, Option<String>>(8)?,
                "priority": r.get::<_, String>(9)?,
                "status": r.get::<_, String>(10)?,
                "completion_note_ar": r.get::<_, Option<String>>(11)?,
                "rev": r.get::<_, i64>(12)?,
                "synced": r.get::<_, i64>(13)? != 0,
            }))
        };
        let rows = match filter {
            Some(f) => stmt.query_map(params![f], map_row),
            None => stmt.query_map([], map_row),
        }
        .map_err(|e| format!("query: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>().map_err(|e| format!("rows: {e}"))
    }

    #[allow(clippy::too_many_arguments)]
    pub fn save_risk(
        &self,
        risk_id: &str,
        hospital_id: &str,
        department_id: Option<&str>,
        title: &str,
        description_ar: Option<&str>,
        category: &str,
        likelihood: i64,
        impact: i64,
        mitigation_ar: Option<&str>,
        owner_name_ar: Option<&str>,
        review_date: Option<&str>,
        at: &str,
    ) -> Result<Value, String> {
        let payload = json!({
            "id": risk_id,
            "department_id": department_id,
            "title": title,
            "description_ar": description_ar,
            "category": category,
            "likelihood": likelihood,
            "impact": impact,
            "mitigation_ar": mitigation_ar,
            "owner_name_ar": owner_name_ar,
            "review_date": review_date,
            "status": "open",
        });
        let mut conn = self.lock()?;
        let tx = conn.transaction().map_err(|e| format!("tx: {e}"))?;
        let base_rev: i64 = tx
            .query_row("SELECT rev FROM local_risk WHERE id = ?1", params![risk_id], |r| r.get(0))
            .optional()
            .map_err(|e| format!("rev read: {e}"))?
            .unwrap_or(0);
        tx.execute(
            "INSERT INTO local_risk(id, hospital_id, department_id, title, description_ar, category,
                                    likelihood, impact, mitigation_ar, owner_name_ar, review_date,
                                    status, rev, updated_at, synced)
             VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,'open',?12,?13,0)
             ON CONFLICT(id) DO UPDATE SET
                department_id = excluded.department_id, title = excluded.title,
                description_ar = excluded.description_ar, category = excluded.category,
                likelihood = excluded.likelihood, impact = excluded.impact,
                mitigation_ar = excluded.mitigation_ar, owner_name_ar = excluded.owner_name_ar,
                review_date = excluded.review_date, updated_at = excluded.updated_at, synced = 0",
            params![
                risk_id, hospital_id, department_id, title, description_ar, category,
                likelihood, impact, mitigation_ar, owner_name_ar, review_date, base_rev + 1, at
            ],
        )
        .map_err(|e| format!("save risk: {e}"))?;
        let op_id = format!("op-{}", uuid::Uuid::new_v4());
        tx.execute(
            "INSERT INTO outbox(id, entity_type, entity_id, op, base_rev, payload, created_at, state)
             VALUES(?1, 'risk', ?2, 'upsert', ?3, ?4, ?5, 'pending')",
            params![op_id, risk_id, base_rev, payload.to_string(), at],
        )
        .map_err(|e| format!("enqueue risk: {e}"))?;
        tx.commit().map_err(|e| format!("commit: {e}"))?;
        Ok(json!({ "risk_id": risk_id, "op_id": op_id }))
    }

    pub fn list_risks(&self, hospital_id: Option<&str>) -> Result<Vec<Value>, String> {
        let conn = self.lock()?;
        let (sql, filter): (&str, Option<&str>) = match hospital_id {
            Some(_) => (
                "SELECT id, hospital_id, department_id, code, title, description_ar, category,
                        likelihood, impact, score, mitigation_ar, owner_name_ar, review_date,
                        status, rev, synced
                 FROM local_risk WHERE hospital_id = ?1 ORDER BY score DESC",
                hospital_id,
            ),
            None => (
                "SELECT id, hospital_id, department_id, code, title, description_ar, category,
                        likelihood, impact, score, mitigation_ar, owner_name_ar, review_date,
                        status, rev, synced
                 FROM local_risk ORDER BY score DESC",
                None,
            ),
        };
        let mut stmt = conn.prepare(sql).map_err(|e| format!("prepare: {e}"))?;
        let map_row = |r: &rusqlite::Row<'_>| {
            Ok(json!({
                "id": r.get::<_, String>(0)?,
                "hospital_id": r.get::<_, Option<String>>(1)?,
                "department_id": r.get::<_, Option<String>>(2)?,
                "code": r.get::<_, Option<String>>(3)?,
                "title": r.get::<_, String>(4)?,
                "description_ar": r.get::<_, Option<String>>(5)?,
                "category": r.get::<_, String>(6)?,
                "likelihood": r.get::<_, i64>(7)?,
                "impact": r.get::<_, i64>(8)?,
                "score": r.get::<_, Option<i64>>(9)?,
                "mitigation_ar": r.get::<_, Option<String>>(10)?,
                "owner_name_ar": r.get::<_, Option<String>>(11)?,
                "review_date": r.get::<_, Option<String>>(12)?,
                "status": r.get::<_, String>(13)?,
                "rev": r.get::<_, i64>(14)?,
                "synced": r.get::<_, i64>(15)? != 0,
            }))
        };
        let rows = match filter {
            Some(f) => stmt.query_map(params![f], map_row),
            None => stmt.query_map([], map_row),
        }
        .map_err(|e| format!("query: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>().map_err(|e| format!("rows: {e}"))
    }

    /// Save an internal audit locally and queue it for sync (v0.15).
    #[allow(clippy::too_many_arguments)]
    pub fn save_audit(
        &self,
        audit_id: &str,
        hospital_id: &str,
        department_id: Option<&str>,
        title: &str,
        standard_ar: Option<&str>,
        scope_ar: Option<&str>,
        auditor_name_ar: Option<&str>,
        audit_date: Option<&str>,
        at: &str,
    ) -> Result<Value, String> {
        let payload = json!({
            "id": audit_id,
            "department_id": department_id,
            "title": title,
            "standard_ar": standard_ar,
            "scope_ar": scope_ar,
            "auditor_name_ar": auditor_name_ar,
            "audit_date": audit_date,
            "status": "planned",
        });
        let mut conn = self.lock()?;
        let tx = conn.transaction().map_err(|e| format!("tx: {e}"))?;
        let base_rev: i64 = tx
            .query_row("SELECT rev FROM local_audit WHERE id = ?1", params![audit_id], |r| r.get(0))
            .optional()
            .map_err(|e| format!("rev read: {e}"))?
            .unwrap_or(0);
        tx.execute(
            "INSERT INTO local_audit(id, hospital_id, department_id, title, standard_ar, scope_ar,
                                     auditor_name_ar, audit_date, status, rev, updated_at, synced)
             VALUES(?1,?2,?3,?4,?5,?6,?7,?8,'planned',?9,?10,0)
             ON CONFLICT(id) DO UPDATE SET
                department_id = excluded.department_id, title = excluded.title,
                standard_ar = excluded.standard_ar, scope_ar = excluded.scope_ar,
                auditor_name_ar = excluded.auditor_name_ar, audit_date = excluded.audit_date,
                updated_at = excluded.updated_at, synced = 0",
            params![
                audit_id, hospital_id, department_id, title, standard_ar, scope_ar,
                auditor_name_ar, audit_date, base_rev + 1, at
            ],
        )
        .map_err(|e| format!("save audit: {e}"))?;
        let op_id = format!("op-{}", uuid::Uuid::new_v4());
        tx.execute(
            "INSERT INTO outbox(id, entity_type, entity_id, op, base_rev, payload, created_at, state)
             VALUES(?1, 'audit', ?2, 'upsert', ?3, ?4, ?5, 'pending')",
            params![op_id, audit_id, base_rev, payload.to_string(), at],
        )
        .map_err(|e| format!("enqueue audit: {e}"))?;
        tx.commit().map_err(|e| format!("commit: {e}"))?;
        Ok(json!({ "audit_id": audit_id, "op_id": op_id }))
    }

    pub fn list_audits(&self, hospital_id: Option<&str>) -> Result<Vec<Value>, String> {
        let conn = self.lock()?;
        let (sql, filter): (&str, Option<&str>) = match hospital_id {
            Some(_) => (
                "SELECT id, hospital_id, department_id, code, title, standard_ar, scope_ar,
                        auditor_name_ar, audit_date, status, score, findings_ar, rev, synced
                 FROM local_audit WHERE hospital_id = ?1 ORDER BY audit_date IS NULL, audit_date DESC",
                hospital_id,
            ),
            None => (
                "SELECT id, hospital_id, department_id, code, title, standard_ar, scope_ar,
                        auditor_name_ar, audit_date, status, score, findings_ar, rev, synced
                 FROM local_audit ORDER BY audit_date IS NULL, audit_date DESC",
                None,
            ),
        };
        let mut stmt = conn.prepare(sql).map_err(|e| format!("prepare: {e}"))?;
        let map_row = |r: &rusqlite::Row<'_>| {
            Ok(json!({
                "id": r.get::<_, String>(0)?,
                "hospital_id": r.get::<_, Option<String>>(1)?,
                "department_id": r.get::<_, Option<String>>(2)?,
                "code": r.get::<_, Option<String>>(3)?,
                "title": r.get::<_, String>(4)?,
                "standard_ar": r.get::<_, Option<String>>(5)?,
                "scope_ar": r.get::<_, Option<String>>(6)?,
                "auditor_name_ar": r.get::<_, Option<String>>(7)?,
                "audit_date": r.get::<_, Option<String>>(8)?,
                "status": r.get::<_, String>(9)?,
                "score": r.get::<_, Option<f64>>(10)?,
                "findings_ar": r.get::<_, Option<String>>(11)?,
                "rev": r.get::<_, i64>(12)?,
                "synced": r.get::<_, i64>(13)? != 0,
            }))
        };
        let rows = match filter {
            Some(f) => stmt.query_map(params![f], map_row),
            None => stmt.query_map([], map_row),
        }
        .map_err(|e| format!("query: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>().map_err(|e| format!("rows: {e}"))
    }

    /// Save an improvement plan locally and queue it for sync (v0.15).
    #[allow(clippy::too_many_arguments)]
    pub fn save_plan(
        &self,
        plan_id: &str,
        hospital_id: &str,
        department_id: Option<&str>,
        title: &str,
        objective_ar: Option<&str>,
        baseline_ar: Option<&str>,
        target_ar: Option<&str>,
        owner_name_ar: Option<&str>,
        start_date: Option<&str>,
        due_date: Option<&str>,
        at: &str,
    ) -> Result<Value, String> {
        let payload = json!({
            "id": plan_id,
            "department_id": department_id,
            "title": title,
            "objective_ar": objective_ar,
            "baseline_ar": baseline_ar,
            "target_ar": target_ar,
            "owner_name_ar": owner_name_ar,
            "start_date": start_date,
            "due_date": due_date,
            "status": "draft",
        });
        let mut conn = self.lock()?;
        let tx = conn.transaction().map_err(|e| format!("tx: {e}"))?;
        let base_rev: i64 = tx
            .query_row("SELECT rev FROM local_plan WHERE id = ?1", params![plan_id], |r| r.get(0))
            .optional()
            .map_err(|e| format!("rev read: {e}"))?
            .unwrap_or(0);
        tx.execute(
            "INSERT INTO local_plan(id, hospital_id, department_id, title, objective_ar, baseline_ar,
                                    target_ar, owner_name_ar, start_date, due_date, status,
                                    rev, updated_at, synced)
             VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,'draft',?11,?12,0)
             ON CONFLICT(id) DO UPDATE SET
                department_id = excluded.department_id, title = excluded.title,
                objective_ar = excluded.objective_ar, baseline_ar = excluded.baseline_ar,
                target_ar = excluded.target_ar, owner_name_ar = excluded.owner_name_ar,
                start_date = excluded.start_date, due_date = excluded.due_date,
                updated_at = excluded.updated_at, synced = 0",
            params![
                plan_id, hospital_id, department_id, title, objective_ar, baseline_ar,
                target_ar, owner_name_ar, start_date, due_date, base_rev + 1, at
            ],
        )
        .map_err(|e| format!("save plan: {e}"))?;
        let op_id = format!("op-{}", uuid::Uuid::new_v4());
        tx.execute(
            "INSERT INTO outbox(id, entity_type, entity_id, op, base_rev, payload, created_at, state)
             VALUES(?1, 'improvement_plan', ?2, 'upsert', ?3, ?4, ?5, 'pending')",
            params![op_id, plan_id, base_rev, payload.to_string(), at],
        )
        .map_err(|e| format!("enqueue plan: {e}"))?;
        tx.commit().map_err(|e| format!("commit: {e}"))?;
        Ok(json!({ "plan_id": plan_id, "op_id": op_id }))
    }

    pub fn list_plans(&self, hospital_id: Option<&str>) -> Result<Vec<Value>, String> {
        let conn = self.lock()?;
        let (sql, filter): (&str, Option<&str>) = match hospital_id {
            Some(_) => (
                "SELECT id, hospital_id, department_id, code, title, objective_ar, baseline_ar,
                        target_ar, owner_name_ar, start_date, due_date, status, rev, synced
                 FROM local_plan WHERE hospital_id = ?1 ORDER BY updated_at DESC",
                hospital_id,
            ),
            None => (
                "SELECT id, hospital_id, department_id, code, title, objective_ar, baseline_ar,
                        target_ar, owner_name_ar, start_date, due_date, status, rev, synced
                 FROM local_plan ORDER BY updated_at DESC",
                None,
            ),
        };
        let mut stmt = conn.prepare(sql).map_err(|e| format!("prepare: {e}"))?;
        let map_row = |r: &rusqlite::Row<'_>| {
            Ok(json!({
                "id": r.get::<_, String>(0)?,
                "hospital_id": r.get::<_, Option<String>>(1)?,
                "department_id": r.get::<_, Option<String>>(2)?,
                "code": r.get::<_, Option<String>>(3)?,
                "title": r.get::<_, String>(4)?,
                "objective_ar": r.get::<_, Option<String>>(5)?,
                "baseline_ar": r.get::<_, Option<String>>(6)?,
                "target_ar": r.get::<_, Option<String>>(7)?,
                "owner_name_ar": r.get::<_, Option<String>>(8)?,
                "start_date": r.get::<_, Option<String>>(9)?,
                "due_date": r.get::<_, Option<String>>(10)?,
                "status": r.get::<_, String>(11)?,
                "rev": r.get::<_, i64>(12)?,
                "synced": r.get::<_, i64>(13)? != 0,
            }))
        };
        let rows = match filter {
            Some(f) => stmt.query_map(params![f], map_row),
            None => stmt.query_map([], map_row),
        }
        .map_err(|e| format!("query: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>().map_err(|e| format!("rows: {e}"))
    }

    /// Save a step under an improvement plan locally and queue it for sync (v0.15).
    #[allow(clippy::too_many_arguments)]
    pub fn save_plan_action(
        &self,
        action_id: &str,
        plan_id: &str,
        title: &str,
        owner_name_ar: Option<&str>,
        due_date: Option<&str>,
        note_ar: Option<&str>,
        at: &str,
    ) -> Result<Value, String> {
        let payload = json!({
            "id": action_id,
            "plan_id": plan_id,
            "title": title,
            "owner_name_ar": owner_name_ar,
            "due_date": due_date,
            "note_ar": note_ar,
            "status": "open",
        });
        let mut conn = self.lock()?;
        let tx = conn.transaction().map_err(|e| format!("tx: {e}"))?;
        let base_rev: i64 = tx
            .query_row("SELECT rev FROM local_plan_action WHERE id = ?1", params![action_id], |r| r.get(0))
            .optional()
            .map_err(|e| format!("rev read: {e}"))?
            .unwrap_or(0);
        tx.execute(
            "INSERT INTO local_plan_action(id, plan_id, title, owner_name_ar, due_date, status, note_ar,
                                           rev, updated_at, synced)
             VALUES(?1,?2,?3,?4,?5,'open',?6,?7,?8,0)
             ON CONFLICT(id) DO UPDATE SET
                title = excluded.title, owner_name_ar = excluded.owner_name_ar,
                due_date = excluded.due_date, note_ar = excluded.note_ar,
                updated_at = excluded.updated_at, synced = 0",
            params![action_id, plan_id, title, owner_name_ar, due_date, note_ar, base_rev + 1, at],
        )
        .map_err(|e| format!("save plan action: {e}"))?;
        let op_id = format!("op-{}", uuid::Uuid::new_v4());
        tx.execute(
            "INSERT INTO outbox(id, entity_type, entity_id, op, base_rev, payload, created_at, state)
             VALUES(?1, 'improvement_action', ?2, 'upsert', ?3, ?4, ?5, 'pending')",
            params![op_id, action_id, base_rev, payload.to_string(), at],
        )
        .map_err(|e| format!("enqueue plan action: {e}"))?;
        tx.commit().map_err(|e| format!("commit: {e}"))?;
        Ok(json!({ "action_id": action_id, "op_id": op_id }))
    }

    pub fn list_plan_actions(&self, plan_id: Option<&str>) -> Result<Vec<Value>, String> {
        let conn = self.lock()?;
        let (sql, filter): (&str, Option<&str>) = match plan_id {
            Some(_) => (
                "SELECT id, plan_id, title, owner_name_ar, due_date, status, note_ar, rev, synced
                 FROM local_plan_action WHERE plan_id = ?1 ORDER BY updated_at",
                plan_id,
            ),
            None => (
                "SELECT id, plan_id, title, owner_name_ar, due_date, status, note_ar, rev, synced
                 FROM local_plan_action ORDER BY updated_at",
                None,
            ),
        };
        let mut stmt = conn.prepare(sql).map_err(|e| format!("prepare: {e}"))?;
        let map_row = |r: &rusqlite::Row<'_>| {
            Ok(json!({
                "id": r.get::<_, String>(0)?,
                "plan_id": r.get::<_, String>(1)?,
                "title": r.get::<_, String>(2)?,
                "owner_name_ar": r.get::<_, Option<String>>(3)?,
                "due_date": r.get::<_, Option<String>>(4)?,
                "status": r.get::<_, String>(5)?,
                "note_ar": r.get::<_, Option<String>>(6)?,
                "rev": r.get::<_, i64>(7)?,
                "synced": r.get::<_, i64>(8)? != 0,
            }))
        };
        let rows = match filter {
            Some(f) => stmt.query_map(params![f], map_row),
            None => stmt.query_map([], map_row),
        }
        .map_err(|e| format!("query: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>().map_err(|e| format!("rows: {e}"))
    }

    pub fn pending(&self, include_failed: bool) -> Result<Vec<PendingOp>, String> {
        let conn = self.lock()?;
        let sql = if include_failed {
            "SELECT id, entity_type, entity_id, op, base_rev, payload, attempts, state, last_error
             FROM outbox WHERE state IN ('pending','failed') ORDER BY created_at"
        } else {
            "SELECT id, entity_type, entity_id, op, base_rev, payload, attempts, state, last_error
             FROM outbox WHERE state = 'pending' ORDER BY created_at"
        };
        let mut stmt = conn.prepare(sql).map_err(|e| format!("prepare: {e}"))?;
        let rows = stmt
            .query_map([], |r| {
                let payload: String = r.get(5)?;
                Ok(PendingOp {
                    op_id: r.get(0)?,
                    entity_type: r.get(1)?,
                    entity_id: r.get(2)?,
                    op: r.get(3)?,
                    base_rev: r.get(4)?,
                    payload: serde_json::from_str(&payload).unwrap_or(Value::Null),
                    attempts: r.get(6)?,
                    state: r.get(7)?,
                    last_error: r.get(8)?,
                })
            })
            .map_err(|e| format!("query: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>().map_err(|e| format!("rows: {e}"))
    }

    /// Record a server result for an op: applied -> synced, else failed.
    pub fn outbox_ack(&self, op_id: &str, status: &str, new_rev: Option<i64>, error: Option<&str>) -> Result<(), String> {
        let conn = self.lock()?;
        if status == "applied" {
            let entity: Option<(String, String)> = conn
                .query_row(
                    "SELECT entity_type, entity_id FROM outbox WHERE id = ?1",
                    params![op_id],
                    |r| Ok((r.get(0)?, r.get(1)?)),
                )
                .optional()
                .map_err(|e| format!("lookup: {e}"))?;
            conn.execute("UPDATE outbox SET state = 'synced' WHERE id = ?1", params![op_id])
                .map_err(|e| format!("ack: {e}"))?;
            if let (Some((entity_type, eid)), Some(rev)) = (entity, new_rev) {
                let table = match entity_type.as_str() {
                    "incident" => "local_incident",
                    "capa_action" => "local_capa",
                    "risk" => "local_risk",
                    "audit" => "local_audit",
                    "improvement_plan" => "local_plan",
                    "improvement_action" => "local_plan_action",
                    _ => "local_value",
                };
                conn.execute(
                    &format!("UPDATE {table} SET synced = 1, rev = ?2 WHERE id = ?1"),
                    params![eid, rev],
                )
                .map_err(|e| format!("mark synced: {e}"))?;
            }
        } else {
            conn.execute(
                "UPDATE outbox SET state = 'failed', attempts = attempts + 1, last_error = ?2 WHERE id = ?1",
                params![op_id, error],
            )
            .map_err(|e| format!("fail: {e}"))?;
        }
        Ok(())
    }

    pub fn bump_attempts(&self, op_id: &str, error: &str) -> Result<(), String> {
        let conn = self.lock()?;
        conn.execute(
            "UPDATE outbox SET attempts = attempts + 1, last_error = ?2 WHERE id = ?1",
            params![op_id, error],
        )
        .map_err(|e| format!("bump: {e}"))?;
        Ok(())
    }

    /// Apply a batch of changes pulled from the server.
    pub fn apply_pull(&self, changes: &[Value], to_seq: i64) -> Result<i64, String> {
        let mut conn = self.lock()?;
        let tx = conn.transaction().map_err(|e| format!("tx: {e}"))?;
        let mut applied = 0i64;
        for change in changes {
            let entity_type = change.get("entity_type").and_then(|v| v.as_str()).unwrap_or("");
            let entity_id = change.get("entity_id").and_then(|v| v.as_str()).unwrap_or("");
            let rev = change.get("rev").and_then(|v| v.as_i64()).unwrap_or(0);
            let op = change.get("op").and_then(|v| v.as_str()).unwrap_or("upsert");
            let payload = change.get("payload").cloned().unwrap_or(Value::Null);
            match entity_type {
                "indicator" => {
                    let code = payload.get("code").and_then(|v| v.as_str()).unwrap_or("");
                    let name_ar = payload.get("name_ar").and_then(|v| v.as_str()).unwrap_or("");
                    tx.execute(
                        "INSERT INTO library(id, kind, code, name_ar, payload) VALUES(?1,'indicator',?2,?3,?4)
                         ON CONFLICT(id) DO UPDATE SET kind='indicator', code=excluded.code, name_ar=excluded.name_ar, payload=excluded.payload",
                        params![entity_id, code, name_ar, payload.to_string()],
                    )
                    .map_err(|e| format!("library: {e}"))?;
                    applied += 1;
                }
                "reporting_period" => {
                    if op == "delete" {
                        tx.execute("DELETE FROM local_period WHERE id = ?1", params![entity_id])
                            .map_err(|e| format!("del period: {e}"))?;
                    } else {
                        tx.execute(
                            "INSERT INTO local_period(id, period_type, year, month, quarter, status, rev, updated_at, synced)
                             VALUES(?1,?2,?3,?4,?5,?6,?7,?8,1)
                             ON CONFLICT(id) DO UPDATE SET status=excluded.status, rev=excluded.rev, updated_at=excluded.updated_at",
                            params![
                                entity_id,
                                payload.get("period_type").and_then(|v| v.as_str()).unwrap_or("monthly"),
                                payload.get("year").and_then(|v| v.as_i64()).unwrap_or(0),
                                payload.get("month").and_then(|v| v.as_i64()),
                                payload.get("quarter").and_then(|v| v.as_i64()),
                                payload.get("status").and_then(|v| v.as_str()).unwrap_or("draft"),
                                rev,
                                payload.get("updated_at").and_then(|v| v.as_str()),
                            ],
                        )
                        .map_err(|e| format!("period: {e}"))?;
                    }
                    applied += 1;
                }
                "indicator_value" => {
                    if op == "delete" {
                        tx.execute("DELETE FROM local_value WHERE id = ?1", params![entity_id])
                            .map_err(|e| format!("del value: {e}"))?;
                    } else {
                        tx.execute(
                            "INSERT INTO local_value(id, period_id, indicator_id, department_id, numerator,
                                                     denominator, value, value_type, rev, updated_at, synced)
                             VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,1)
                             ON CONFLICT(id) DO UPDATE SET numerator=excluded.numerator, denominator=excluded.denominator,
                                value=excluded.value, value_type=excluded.value_type, rev=excluded.rev,
                                updated_at=excluded.updated_at, synced=1",
                            params![
                                entity_id,
                                payload.get("period_id").and_then(|v| v.as_str()),
                                payload.get("indicator_id").and_then(|v| v.as_str()),
                                payload.get("department_id").and_then(|v| v.as_str()),
                                payload.get("numerator").and_then(|v| v.as_f64()),
                                payload.get("denominator").and_then(|v| v.as_f64()),
                                payload.get("value").and_then(|v| v.as_f64()),
                                payload.get("value_type").and_then(|v| v.as_str()).unwrap_or("computed"),
                                rev,
                                payload.get("updated_at").and_then(|v| v.as_str()),
                            ],
                        )
                        .map_err(|e| format!("value: {e}"))?;
                    }
                    applied += 1;
                }
                "incident" => {
                    if op == "delete" {
                        tx.execute("DELETE FROM local_incident WHERE id = ?1", params![entity_id])
                            .map_err(|e| format!("del incident: {e}"))?;
                    } else {
                        tx.execute(
                            "INSERT INTO local_incident(id, hospital_id, department_id, code, title, description,
                                                        incident_type, severity, patient_harm, occurred_at,
                                                        reported_at, is_anonymous, status, immediate_action,
                                                        rev, updated_at, synced)
                             VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14,?15,?16,1)
                             ON CONFLICT(id) DO UPDATE SET code=excluded.code, status=excluded.status,
                                title=excluded.title, description=excluded.description,
                                incident_type=excluded.incident_type, severity=excluded.severity,
                                patient_harm=excluded.patient_harm, occurred_at=excluded.occurred_at,
                                is_anonymous=excluded.is_anonymous, immediate_action=excluded.immediate_action,
                                rev=excluded.rev, updated_at=excluded.updated_at, synced=1",
                            params![
                                entity_id,
                                payload.get("hospital_id").and_then(|v| v.as_str()),
                                payload.get("department_id").and_then(|v| v.as_str()),
                                payload.get("code").and_then(|v| v.as_str()),
                                payload.get("title").and_then(|v| v.as_str()).unwrap_or(""),
                                payload.get("description").and_then(|v| v.as_str()),
                                payload.get("incident_type").and_then(|v| v.as_str()).unwrap_or("other"),
                                payload.get("severity").and_then(|v| v.as_str()).unwrap_or("moderate"),
                                payload.get("patient_harm").and_then(|v| v.as_str()).unwrap_or("none"),
                                payload.get("occurred_at").and_then(|v| v.as_str()),
                                payload.get("reported_at").and_then(|v| v.as_str()),
                                payload.get("is_anonymous").and_then(|v| v.as_bool()).unwrap_or(false) as i64,
                                payload.get("status").and_then(|v| v.as_str()).unwrap_or("reported"),
                                payload.get("immediate_action").and_then(|v| v.as_str()),
                                rev,
                                payload.get("updated_at").and_then(|v| v.as_str()),
                            ],
                        )
                        .map_err(|e| format!("incident: {e}"))?;
                    }
                    applied += 1;
                }
                "capa_action" => {
                    if op == "delete" {
                        tx.execute("DELETE FROM local_capa WHERE id = ?1", params![entity_id])
                            .map_err(|e| format!("del capa: {e}"))?;
                    } else {
                        tx.execute(
                            "INSERT INTO local_capa(id, hospital_id, department_id, incident_id, kind, title,
                                                    description_ar, owner_name_ar, due_date, priority, status,
                                                    completion_note_ar, rev, updated_at, synced)
                             VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14,1)
                             ON CONFLICT(id) DO UPDATE SET
                                department_id=excluded.department_id, incident_id=excluded.incident_id,
                                kind=excluded.kind, title=excluded.title,
                                description_ar=excluded.description_ar, owner_name_ar=excluded.owner_name_ar,
                                due_date=excluded.due_date, priority=excluded.priority, status=excluded.status,
                                completion_note_ar=excluded.completion_note_ar,
                                rev=excluded.rev, updated_at=excluded.updated_at, synced=1",
                            params![
                                entity_id,
                                payload.get("hospital_id").and_then(|v| v.as_str()),
                                payload.get("department_id").and_then(|v| v.as_str()),
                                payload.get("incident_id").and_then(|v| v.as_str()),
                                payload.get("kind").and_then(|v| v.as_str()).unwrap_or("corrective"),
                                payload.get("title").and_then(|v| v.as_str()).unwrap_or(""),
                                payload.get("description_ar").and_then(|v| v.as_str()),
                                payload.get("owner_name_ar").and_then(|v| v.as_str()),
                                payload.get("due_date").and_then(|v| v.as_str()),
                                payload.get("priority").and_then(|v| v.as_str()).unwrap_or("medium"),
                                payload.get("status").and_then(|v| v.as_str()).unwrap_or("open"),
                                payload.get("completion_note_ar").and_then(|v| v.as_str()),
                                rev,
                                payload.get("updated_at").and_then(|v| v.as_str()),
                            ],
                        )
                        .map_err(|e| format!("capa: {e}"))?;
                    }
                    applied += 1;
                }
                "risk" => {
                    if op == "delete" {
                        tx.execute("DELETE FROM local_risk WHERE id = ?1", params![entity_id])
                            .map_err(|e| format!("del risk: {e}"))?;
                    } else {
                        tx.execute(
                            "INSERT INTO local_risk(id, hospital_id, department_id, code, title, description_ar,
                                                    category, likelihood, impact, score, mitigation_ar,
                                                    owner_name_ar, review_date, status, rev, updated_at, synced)
                             VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14,?15,?16,1)
                             ON CONFLICT(id) DO UPDATE SET
                                department_id=excluded.department_id, code=excluded.code, title=excluded.title,
                                description_ar=excluded.description_ar, category=excluded.category,
                                likelihood=excluded.likelihood, impact=excluded.impact, score=excluded.score,
                                mitigation_ar=excluded.mitigation_ar, owner_name_ar=excluded.owner_name_ar,
                                review_date=excluded.review_date, status=excluded.status,
                                rev=excluded.rev, updated_at=excluded.updated_at, synced=1",
                            params![
                                entity_id,
                                payload.get("hospital_id").and_then(|v| v.as_str()),
                                payload.get("department_id").and_then(|v| v.as_str()),
                                payload.get("code").and_then(|v| v.as_str()),
                                payload.get("title").and_then(|v| v.as_str()).unwrap_or(""),
                                payload.get("description_ar").and_then(|v| v.as_str()),
                                payload.get("category").and_then(|v| v.as_str()).unwrap_or("clinical"),
                                payload.get("likelihood").and_then(|v| v.as_i64()).unwrap_or(3),
                                payload.get("impact").and_then(|v| v.as_i64()).unwrap_or(3),
                                payload.get("score").and_then(|v| v.as_i64()),
                                payload.get("mitigation_ar").and_then(|v| v.as_str()),
                                payload.get("owner_name_ar").and_then(|v| v.as_str()),
                                payload.get("review_date").and_then(|v| v.as_str()),
                                payload.get("status").and_then(|v| v.as_str()).unwrap_or("open"),
                                rev,
                                payload.get("updated_at").and_then(|v| v.as_str()),
                            ],
                        )
                        .map_err(|e| format!("risk: {e}"))?;
                    }
                    applied += 1;
                }
                "audit" => {
                    if op == "delete" {
                        tx.execute("DELETE FROM local_audit WHERE id = ?1", params![entity_id])
                            .map_err(|e| format!("del audit: {e}"))?;
                    } else {
                        tx.execute(
                            "INSERT INTO local_audit(id, hospital_id, department_id, code, title, standard_ar,
                                                     scope_ar, auditor_name_ar, audit_date, status, score,
                                                     findings_ar, rev, updated_at, synced)
                             VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14,1)
                             ON CONFLICT(id) DO UPDATE SET
                                department_id=excluded.department_id, code=excluded.code, title=excluded.title,
                                standard_ar=excluded.standard_ar, scope_ar=excluded.scope_ar,
                                auditor_name_ar=excluded.auditor_name_ar, audit_date=excluded.audit_date,
                                status=excluded.status, score=excluded.score, findings_ar=excluded.findings_ar,
                                rev=excluded.rev, updated_at=excluded.updated_at, synced=1",
                            params![
                                entity_id,
                                payload.get("hospital_id").and_then(|v| v.as_str()),
                                payload.get("department_id").and_then(|v| v.as_str()),
                                payload.get("code").and_then(|v| v.as_str()),
                                payload.get("title").and_then(|v| v.as_str()).unwrap_or(""),
                                payload.get("standard_ar").and_then(|v| v.as_str()),
                                payload.get("scope_ar").and_then(|v| v.as_str()),
                                payload.get("auditor_name_ar").and_then(|v| v.as_str()),
                                payload.get("audit_date").and_then(|v| v.as_str()),
                                payload.get("status").and_then(|v| v.as_str()).unwrap_or("planned"),
                                payload.get("score").and_then(|v| v.as_f64()),
                                payload.get("findings_ar").and_then(|v| v.as_str()),
                                rev,
                                payload.get("updated_at").and_then(|v| v.as_str()),
                            ],
                        )
                        .map_err(|e| format!("audit: {e}"))?;
                    }
                    applied += 1;
                }
                "improvement_plan" => {
                    if op == "delete" {
                        tx.execute("DELETE FROM local_plan WHERE id = ?1", params![entity_id])
                            .map_err(|e| format!("del plan: {e}"))?;
                    } else {
                        tx.execute(
                            "INSERT INTO local_plan(id, hospital_id, department_id, code, title, objective_ar,
                                                    baseline_ar, target_ar, owner_name_ar, start_date, due_date,
                                                    status, rev, updated_at, synced)
                             VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14,1)
                             ON CONFLICT(id) DO UPDATE SET
                                department_id=excluded.department_id, code=excluded.code, title=excluded.title,
                                objective_ar=excluded.objective_ar, baseline_ar=excluded.baseline_ar,
                                target_ar=excluded.target_ar, owner_name_ar=excluded.owner_name_ar,
                                start_date=excluded.start_date, due_date=excluded.due_date, status=excluded.status,
                                rev=excluded.rev, updated_at=excluded.updated_at, synced=1",
                            params![
                                entity_id,
                                payload.get("hospital_id").and_then(|v| v.as_str()),
                                payload.get("department_id").and_then(|v| v.as_str()),
                                payload.get("code").and_then(|v| v.as_str()),
                                payload.get("title").and_then(|v| v.as_str()).unwrap_or(""),
                                payload.get("objective_ar").and_then(|v| v.as_str()),
                                payload.get("baseline_ar").and_then(|v| v.as_str()),
                                payload.get("target_ar").and_then(|v| v.as_str()),
                                payload.get("owner_name_ar").and_then(|v| v.as_str()),
                                payload.get("start_date").and_then(|v| v.as_str()),
                                payload.get("due_date").and_then(|v| v.as_str()),
                                payload.get("status").and_then(|v| v.as_str()).unwrap_or("draft"),
                                rev,
                                payload.get("updated_at").and_then(|v| v.as_str()),
                            ],
                        )
                        .map_err(|e| format!("plan: {e}"))?;
                    }
                    applied += 1;
                }
                "improvement_action" => {
                    if op == "delete" {
                        tx.execute("DELETE FROM local_plan_action WHERE id = ?1", params![entity_id])
                            .map_err(|e| format!("del plan action: {e}"))?;
                    } else {
                        tx.execute(
                            "INSERT INTO local_plan_action(id, plan_id, title, owner_name_ar, due_date, status,
                                                           note_ar, rev, updated_at, synced)
                             VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,1)
                             ON CONFLICT(id) DO UPDATE SET
                                title=excluded.title, owner_name_ar=excluded.owner_name_ar,
                                due_date=excluded.due_date, status=excluded.status, note_ar=excluded.note_ar,
                                rev=excluded.rev, updated_at=excluded.updated_at, synced=1",
                            params![
                                entity_id,
                                payload.get("plan_id").and_then(|v| v.as_str()).unwrap_or(""),
                                payload.get("title").and_then(|v| v.as_str()).unwrap_or(""),
                                payload.get("owner_name_ar").and_then(|v| v.as_str()),
                                payload.get("due_date").and_then(|v| v.as_str()),
                                payload.get("status").and_then(|v| v.as_str()).unwrap_or("open"),
                                payload.get("note_ar").and_then(|v| v.as_str()),
                                rev,
                                payload.get("updated_at").and_then(|v| v.as_str()),
                            ],
                        )
                        .map_err(|e| format!("plan action: {e}"))?;
                    }
                    applied += 1;
                }
                _ => {}
            }
        }
        Self::meta_set(&tx, "cursor", &to_seq.to_string())?;
        tx.commit().map_err(|e| format!("commit pull: {e}"))?;
        Ok(applied)
    }

    /// Cache the national indicator library from a bootstrap response.
    pub fn cache_library(&self, indicators: &[Value]) -> Result<usize, String> {
        let mut conn = self.lock()?;
        let tx = conn.transaction().map_err(|e| format!("tx: {e}"))?;
        let mut count = 0usize;
        for ind in indicators {
            let id = ind.get("id").and_then(|v| v.as_str()).unwrap_or("");
            if id.is_empty() {
                continue;
            }
            let code = ind.get("code").and_then(|v| v.as_str()).unwrap_or("");
            let name_ar = ind.get("name_ar").and_then(|v| v.as_str()).unwrap_or("");
            tx.execute(
                "INSERT INTO library(id, kind, code, name_ar, payload) VALUES(?1,'indicator',?2,?3,?4)
                 ON CONFLICT(id) DO UPDATE SET kind='indicator', code=excluded.code, name_ar=excluded.name_ar, payload=excluded.payload",
                params![id, code, name_ar, ind.to_string()],
            )
            .map_err(|e| format!("cache: {e}"))?;
            count += 1;
        }
        tx.commit().map_err(|e| format!("commit cache: {e}"))?;
        Ok(count)
    }

    pub fn library(&self) -> Result<Vec<Value>, String> {
        let conn = self.lock()?;
        let mut stmt = conn
            .prepare("SELECT payload FROM library WHERE kind = 'indicator' ORDER BY code")
            .map_err(|e| format!("prepare: {e}"))?;
        let rows = stmt
            .query_map([], |r| {
                let payload: String = r.get(0)?;
                Ok(serde_json::from_str::<Value>(&payload).unwrap_or(Value::Null))
            })
            .map_err(|e| format!("query: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>().map_err(|e| format!("rows: {e}"))
    }

    pub fn record_conflict(&self, op_id: &str, entity_type: &str, entity_id: &str, local: &Value, server: &Value, at: &str) -> Result<(), String> {
        let conn = self.lock()?;
        let id = format!("cf-{}", uuid::Uuid::new_v4());
        conn.execute(
            "INSERT INTO conflict(id, entity_type, entity_id, local_payload, server_payload, resolution, created_at)
             VALUES(?1,?2,?3,?4,?5,'auto_server',?6)",
            params![id, entity_type, entity_id, local.to_string(), server.to_string(), at],
        )
        .map_err(|e| format!("conflict: {e}"))?;
        conn.execute("UPDATE outbox SET state = 'synced', last_error = 'conflict' WHERE id = ?1", params![op_id])
            .map_err(|e| format!("resolve op: {e}"))?;
        Ok(())
    }

    pub fn conflicts(&self) -> Result<Vec<Value>, String> {
        let conn = self.lock()?;
        let mut stmt = conn
            .prepare("SELECT id, entity_type, entity_id, resolution, created_at FROM conflict ORDER BY created_at DESC")
            .map_err(|e| format!("prepare: {e}"))?;
        let rows = stmt
            .query_map([], |r| {
                Ok(json!({
                    "id": r.get::<_, String>(0)?,
                    "entity_type": r.get::<_, String>(1)?,
                    "entity_id": r.get::<_, String>(2)?,
                    "resolution": r.get::<_, String>(3)?,
                    "created_at": r.get::<_, String>(4)?,
                }))
            })
            .map_err(|e| format!("query: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>().map_err(|e| format!("rows: {e}"))
    }

    /// Full local backup as a JSON document (library + pending/failed outbox).
    pub fn export_backup(&self) -> Result<Value, String> {
        let library = {
            let conn = self.lock()?;
            let mut stmt = conn.prepare("SELECT payload FROM library WHERE kind = 'indicator'").map_err(|e| e.to_string())?;
            let rows = stmt.query_map([], |r| r.get::<_, String>(0)).map_err(|e| e.to_string())?;
            rows.filter_map(|r| r.ok())
                .map(|s| serde_json::from_str::<Value>(&s).unwrap_or(Value::Null))
                .collect::<Vec<_>>()
        };
        let outbox = self.pending(true)?;
        Ok(json!({
            "version": 1,
            "exported_at": now_iso(),
            "library": library,
            "outbox": outbox.iter().map(|o| json!({
                "op_id": o.op_id, "entity_type": o.entity_type, "entity_id": o.entity_id,
                "op": o.op, "base_rev": o.base_rev, "payload": o.payload, "state": o.state,
            })).collect::<Vec<_>>(),
        }))
    }
}

#[derive(Deserialize)]
pub struct SaveValueInput {
    pub period_id: String,
    pub indicator_id: String,
    pub department_id: Option<String>,
    pub numerator: Option<f64>,
    pub denominator: Option<f64>,
    pub entered_value: Option<f64>,
    pub computation: String,
    #[serde(default)]
    pub multiplier: Option<f64>,
    pub direction: String,
    pub target_value: Option<f64>,
    pub acceptable_min: Option<f64>,
    pub acceptable_max: Option<f64>,
    pub note: Option<String>,
    #[serde(default)]
    pub value_id: Option<String>,
}

pub fn now_iso() -> String {
    // Seconds-precision ISO-8601 in UTC, computed without extra dependencies.
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let (days, rem) = (secs / 86_400, secs % 86_400);
    let (h, m, s) = (rem / 3600, (rem % 3600) / 60, rem % 60);
    // Civil date from days since 1970-01-01 (Howard Hinnant's algorithm).
    let z = days as i64 + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = (z - era * 146_097) as i64;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = if month <= 2 { y + 1 } else { y };
    format!("{year:04}-{month:02}-{d:02}T{h:02}:{m:02}:{s:02}Z")
}

/// Compute a value exactly like the server's engine (docs/15).
pub fn compute_value(
    computation: &str,
    numerator: Option<f64>,
    denominator: Option<f64>,
    multiplier: Option<f64>,
    entered_value: Option<f64>,
) -> (Option<f64>, String) {
    match computation {
        "count" | "sum" | "entered" => (entered_value, "entered".to_string()),
        "ratio" | "rate" | "percent" | "average" => {
            let (num, den) = match (numerator, denominator) {
                (Some(n), Some(d)) if d != 0.0 => (n, d),
                _ => return (None, "computed".to_string()),
            };
            let mult = multiplier.filter(|m| *m != 0.0).unwrap_or(1.0);
            let raw = (num / den) * mult;
            let rounded = (raw * 10_000.0).round() / 10_000.0;
            (Some(rounded), "computed".to_string())
        }
        _ => (None, "computed".to_string()),
    }
}

/// Judge a value against its target, mirroring the server's assess().
pub fn assess(
    direction: &str,
    value: Option<f64>,
    target_value: Option<f64>,
    acceptable_min: Option<f64>,
    acceptable_max: Option<f64>,
) -> (String, String) {
    let value = match value {
        Some(v) => v,
        None => return ("unknown".into(), "غير محسوب".into()),
    };
    match direction {
        "higher_better" => {
            if let Some(min) = acceptable_min {
                if value < min {
                    return ("poor".into(), "أقل من الحد المقبول".into());
                }
            }
            if let Some(t) = target_value {
                if value >= t {
                    return ("good".into(), "محقق للهدف".into());
                }
            }
            ("warning".into(), "دون الهدف".into())
        }
        "lower_better" => {
            if let Some(max) = acceptable_max {
                if value > max {
                    return ("poor".into(), "أعلى من الحد المقبول".into());
                }
            }
            if let Some(t) = target_value {
                if value <= t {
                    return ("good".into(), "محقق للهدف".into());
                }
            }
            ("warning".into(), "أعلى من الهدف".into())
        }
        "target_range" => {
            let below = acceptable_min.map(|m| value < m).unwrap_or(false);
            let above = acceptable_max.map(|m| value > m).unwrap_or(false);
            if below || above {
                return ("poor".into(), "خارج النطاق المقبول".into());
            }
            if let Some(t) = target_value {
                let lo = acceptable_min.unwrap_or(t);
                let hi = acceptable_max.unwrap_or(t);
                let span = (hi - lo).abs();
                let span = if span == 0.0 { t.abs().max(1.0) } else { span };
                if (value - t).abs() <= 0.1 * span {
                    return ("good".into(), "قريب من الهدف".into());
                }
            }
            ("warning".into(), "داخل النطاق".into())
        }
        _ => ("unknown".into(), "غير معروف".into()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_store(name: &str) -> Store {
        let mut path = std::env::temp_dir();
        path.push(format!("yhq-test-{}-{}.sqlite", name, uuid::Uuid::new_v4()));
        Store::open(path).expect("open store")
    }

    #[test]
    fn compute_matches_server_rules() {
        assert_eq!(compute_value("ratio", Some(18.0), Some(20.0), Some(100.0), None), (Some(90.0), "computed".into()));
        // zero denominator never divides: it yields no value, not a crash
        assert_eq!(compute_value("ratio", Some(3.0), Some(0.0), Some(100.0), None), (None, "computed".into()));
        assert_eq!(compute_value("count", None, None, None, Some(7.0)), (Some(7.0), "entered".into()));
    }

    #[test]
    fn assess_respects_direction() {
        // lower is better: a rate below target is good, above is a warning
        assert_eq!(assess("lower_better", Some(1.0), Some(2.0), None, None).0, "good");
        assert_eq!(assess("lower_better", Some(5.0), Some(2.0), None, None).0, "warning");
        // higher is better
        assert_eq!(assess("higher_better", Some(95.0), Some(90.0), None, None).0, "good");
        // no value -> unknown, never invented
        assert_eq!(assess("higher_better", None, Some(90.0), None, None).0, "unknown");
    }

    #[test]
    fn save_value_queues_an_outbox_op() {
        let s = temp_store("save");
        let out = s
            .save_value("v1", "p1", "i1", None, Some(18.0), Some(20.0), None, "ratio",
                        Some(100.0), "higher_better", Some(90.0), None, None, None, "2026-01-01T00:00:00Z")
            .expect("save");
        assert_eq!(out["value"].as_f64(), Some(90.0));
        assert_eq!(out["assessment"].as_str(), Some("good"));
        let pending = s.pending(false).expect("pending");
        assert_eq!(pending.len(), 1);
        assert_eq!(pending[0].entity_type, "indicator_value");
        assert_eq!(pending[0].base_rev, 0);
    }

    #[test]
    fn resaving_bumps_base_rev_for_conflict_detection() {
        let s = temp_store("rev");
        s.save_value("v1", "p1", "i1", None, Some(1.0), Some(2.0), None, "ratio",
                     Some(100.0), "higher_better", None, None, None, None, "t1").unwrap();
        s.save_value("v1", "p1", "i1", None, Some(3.0), Some(4.0), None, "ratio",
                     Some(100.0), "higher_better", None, None, None, None, "t2").unwrap();
        let pending = s.pending(false).unwrap();
        assert_eq!(pending.len(), 2); // one op per edit, in order
        assert_eq!(pending[1].base_rev, 1); // second edit knows the server rev is 1
    }

    #[test]
    fn ack_applied_clears_the_queue() {
        let s = temp_store("ack");
        let out = s.save_value("v1", "p1", "i1", None, Some(18.0), Some(20.0), None, "ratio",
                               Some(100.0), "higher_better", Some(90.0), None, None, None, "t").unwrap();
        let op_id = out["op_id"].as_str().unwrap().to_string();
        s.outbox_ack(&op_id, "applied", Some(2), None).unwrap();
        assert_eq!(s.pending(false).unwrap().len(), 0);
        assert_eq!(s.status().unwrap().pending_count, 0);
    }

    #[test]
    fn rejected_op_is_kept_as_failed_for_the_user() {
        let s = temp_store("rej");
        let out = s.save_value("v1", "p1", "i1", None, Some(18.0), Some(20.0), None, "ratio",
                               Some(100.0), "higher_better", Some(90.0), None, None, None, "t").unwrap();
        let op_id = out["op_id"].as_str().unwrap().to_string();
        s.outbox_ack(&op_id, "rejected", None, Some("already_approved")).unwrap();
        assert_eq!(s.pending(false).unwrap().len(), 0); // no longer pending
        assert_eq!(s.pending(true).unwrap().len(), 1); // but still visible as failed
        assert_eq!(s.status().unwrap().failed_count, 1);
    }

    #[test]
    fn pull_updates_cursor_and_caches_library() {
        let s = temp_store("pull");
        let changes = vec![
            json!({"server_seq": 5, "entity_type": "indicator", "entity_id": "i1", "op": "upsert", "rev": 1,
                   "payload": {"id": "i1", "code": "PS-INF", "name_ar": "معدل العدوى"}}),
            json!({"server_seq": 6, "entity_type": "reporting_period", "entity_id": "p1", "op": "upsert", "rev": 1,
                   "payload": {"period_type": "monthly", "year": 2026, "month": 1, "status": "draft"}}),
        ];
        let applied = s.apply_pull(&changes, 6).unwrap();
        assert_eq!(applied, 2);
        assert_eq!(s.status().unwrap().cursor, 6);
        assert_eq!(s.library().unwrap().len(), 1);
    }

    #[test]
    fn conflict_is_recorded_not_lost() {
        let s = temp_store("conflict");
        let out = s.save_value("v1", "p1", "i1", None, Some(1.0), Some(2.0), None, "ratio",
                               Some(100.0), "higher_better", None, None, None, None, "t").unwrap();
        let op_id = out["op_id"].as_str().unwrap().to_string();
        s.record_conflict(&op_id, "indicator_value", "v1", &json!({"numerator": 1.0}), &json!({"numerator": 15.0}), "t").unwrap();
        assert_eq!(s.conflicts().unwrap().len(), 1);
        assert_eq!(s.status().unwrap().conflict_count, 1);
        assert_eq!(s.pending(false).unwrap().len(), 0);
    }

    #[test]
    fn create_period_queues_and_lists() {
        let s = temp_store("period");
        let out = s.create_period("p1", "h1", "monthly", 2026, Some(1), None, "t").unwrap();
        assert_eq!(out["period_id"].as_str(), Some("p1"));
        let periods = s.list_periods(Some("h1")).unwrap();
        assert_eq!(periods.len(), 1);
        assert_eq!(periods[0]["status"].as_str(), Some("draft"));
        assert_eq!(s.pending(false).unwrap().len(), 1);
        assert_eq!(s.pending(false).unwrap()[0].entity_type, "reporting_period");
    }

    #[test]
    fn save_incident_queues_an_outbox_op_and_lists_locally() {
        let s = temp_store("incident");
        let out = s
            .save_incident(
                "inc1", "h1", None, "سقوط مريض", Some("سقط أثناء النقل"), "fall",
                "moderate", "mild", Some("2026-02-01T10:00:00Z"), false,
                Some("أُسعف فوراً"), "2026-02-01T10:05:00Z",
            )
            .expect("save incident");
        assert_eq!(out["incident_id"].as_str(), Some("inc1"));

        let rows = s.list_incidents(Some("h1")).expect("list");
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["severity"].as_str(), Some("moderate"));
        assert_eq!(rows[0]["status"].as_str(), Some("reported"));
        // The code is server-owned, so the local row has none yet.
        assert!(rows[0]["code"].is_null());

        let pending = s.pending(false).expect("pending");
        assert_eq!(pending.len(), 1);
        assert_eq!(pending[0].entity_type, "incident");
        assert_eq!(pending[0].base_rev, 0);
    }

    #[test]
    fn editing_an_incident_bumps_base_rev_for_conflict_detection() {
        let s = temp_store("incident-rev");
        s.save_incident("inc1", "h1", None, "حادث", None, "fall", "minor", "none",
                        None, false, None, "t1").unwrap();
        s.save_incident("inc1", "h1", None, "حادث محدّث", None, "fall", "major", "moderate",
                        None, false, None, "t2").unwrap();
        let pending = s.pending(false).unwrap();
        assert_eq!(pending.len(), 2); // one op per edit, in order
        assert_eq!(pending[1].base_rev, 1); // the second edit knows the server rev is 1
        let rows = s.list_incidents(Some("h1")).unwrap();
        assert_eq!(rows.len(), 1); // still one row, updated in place
        assert_eq!(rows[0]["severity"].as_str(), Some("major"));
    }

    #[test]
    fn ack_applied_marks_a_local_incident_synced_with_the_server_rev() {
        let s = temp_store("incident-ack");
        let out = s
            .save_incident("inc1", "h1", None, "حادث", None, "fall", "minor", "none",
                           None, false, None, "t")
            .unwrap();
        let op_id = out["op_id"].as_str().unwrap().to_string();
        s.outbox_ack(&op_id, "applied", Some(2), None).unwrap();
        assert_eq!(s.pending(false).unwrap().len(), 0);
        let rows = s.list_incidents(Some("h1")).unwrap();
        assert_eq!(rows[0]["synced"].as_bool(), Some(true));
        assert_eq!(rows[0]["rev"].as_i64(), Some(2));
    }

    #[test]
    fn pull_applies_a_server_incident_with_its_code_and_status() {
        let s = temp_store("incident-pull");
        let changes = vec![json!({
            "server_seq": 9, "entity_type": "incident", "entity_id": "inc9", "op": "upsert", "rev": 3,
            "payload": {
                "id": "inc9", "hospital_id": "h1", "code": "INC-2026-0009", "title": "حادث من الخادم",
                "incident_type": "medication", "severity": "major", "patient_harm": "severe",
                "status": "under_review", "is_anonymous": false, "reported_at": "2026-02-02T08:00:00Z"
            }
        })];
        assert_eq!(s.apply_pull(&changes, 9).unwrap(), 1);
        let rows = s.list_incidents(Some("h1")).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["code"].as_str(), Some("INC-2026-0009"));
        assert_eq!(rows[0]["status"].as_str(), Some("under_review"));
        assert_eq!(rows[0]["synced"].as_bool(), Some(true));
    }

    #[test]
    fn save_capa_queues_an_outbox_op_and_lists_locally() {
        let s = temp_store("capa");
        let out = s
            .save_capa("cap1", "h1", None, None, "corrective", "تدريب الكادر",
                       Some("تدريب على التحقق من الهوية"), Some("مسؤول الجودة"),
                       Some("2026-06-30"), "high", "2026-03-01T09:00:00Z")
            .expect("save capa");
        assert_eq!(out["capa_id"].as_str(), Some("cap1"));

        let rows = s.list_capa(Some("h1")).expect("list");
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["priority"].as_str(), Some("high"));
        assert_eq!(rows[0]["status"].as_str(), Some("open"));
        assert_eq!(rows[0]["kind"].as_str(), Some("corrective"));

        let pending = s.pending(false).expect("pending");
        assert_eq!(pending.len(), 1);
        assert_eq!(pending[0].entity_type, "capa_action");
    }

    #[test]
    fn ack_applied_marks_a_local_capa_synced() {
        let s = temp_store("capa-ack");
        let out = s
            .save_capa("cap1", "h1", None, None, "preventive", "إجراء وقائي", None, None,
                       None, "medium", "t")
            .unwrap();
        let op_id = out["op_id"].as_str().unwrap().to_string();
        s.outbox_ack(&op_id, "applied", Some(4), None).unwrap();
        assert_eq!(s.pending(false).unwrap().len(), 0);
        let rows = s.list_capa(Some("h1")).unwrap();
        assert_eq!(rows[0]["synced"].as_bool(), Some(true));
        assert_eq!(rows[0]["rev"].as_i64(), Some(4));
    }

    #[test]
    fn pull_applies_a_server_capa_with_status_and_note() {
        let s = temp_store("capa-pull");
        let changes = vec![json!({
            "server_seq": 3, "entity_type": "capa_action", "entity_id": "cap9", "op": "upsert", "rev": 2,
            "payload": {
                "id": "cap9", "hospital_id": "h1", "kind": "corrective", "title": "إجراء من الخادم",
                "priority": "critical", "status": "done", "completion_note_ar": "نُفّذ",
                "due_date": "2026-05-01"
            }
        })];
        assert_eq!(s.apply_pull(&changes, 3).unwrap(), 1);
        let rows = s.list_capa(Some("h1")).unwrap();
        assert_eq!(rows[0]["status"].as_str(), Some("done"));
        assert_eq!(rows[0]["completion_note_ar"].as_str(), Some("نُفّذ"));
        assert_eq!(rows[0]["synced"].as_bool(), Some(true));
    }

    #[test]
    fn save_risk_queues_an_outbox_op_and_lists_locally() {
        let s = temp_store("risk");
        let out = s
            .save_risk("rsk1", "h1", None, "خطر العدوى", Some("وصف"), "infection", 4, 5,
                       Some("تعقيم"), Some("مسؤول مكافحة العدوى"), Some("2026-07-15"),
                       "2026-03-01T09:00:00Z")
            .expect("save risk");
        assert_eq!(out["risk_id"].as_str(), Some("rsk1"));

        let rows = s.list_risks(Some("h1")).expect("list");
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["category"].as_str(), Some("infection"));
        assert_eq!(rows[0]["likelihood"].as_i64(), Some(4));
        // The score is computed on the server, so the local row has none yet.
        assert!(rows[0]["score"].is_null());

        let pending = s.pending(false).expect("pending");
        assert_eq!(pending[0].entity_type, "risk");
    }

    #[test]
    fn pull_applies_a_server_risk_with_code_and_score() {
        let s = temp_store("risk-pull");
        let changes = vec![json!({
            "server_seq": 5, "entity_type": "risk", "entity_id": "rsk9", "op": "upsert", "rev": 1,
            "payload": {
                "id": "rsk9", "hospital_id": "h1", "code": "RSK-2026-0009", "title": "خطر من الخادم",
                "category": "clinical", "likelihood": 4, "impact": 5, "score": 20, "status": "open"
            }
        })];
        assert_eq!(s.apply_pull(&changes, 5).unwrap(), 1);
        let rows = s.list_risks(Some("h1")).unwrap();
        assert_eq!(rows[0]["code"].as_str(), Some("RSK-2026-0009"));
        assert_eq!(rows[0]["score"].as_i64(), Some(20));
        assert_eq!(rows[0]["synced"].as_bool(), Some(true));
    }

    #[test]
    fn save_audit_queues_an_outbox_op_and_lists_locally() {
        let s = temp_store("audit");
        let out = s
            .save_audit("aud1", "h1", None, "تدقيق مكافحة العدوى", Some("معايير العدوى"),
                        Some("قسم العمليات"), Some("فريق الجودة"), Some("2026-06-15"),
                        "2026-03-01T09:00:00Z")
            .expect("save audit");
        assert_eq!(out["audit_id"].as_str(), Some("aud1"));

        let rows = s.list_audits(Some("h1")).expect("list");
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["status"].as_str(), Some("planned"));
        assert_eq!(rows[0]["standard_ar"].as_str(), Some("معايير العدوى"));
        // The code and score are server-owned, so the local row has neither yet.
        assert!(rows[0]["code"].is_null());
        assert!(rows[0]["score"].is_null());

        let pending = s.pending(false).expect("pending");
        assert_eq!(pending[0].entity_type, "audit");
    }

    #[test]
    fn pull_applies_a_server_audit_with_code_and_score() {
        let s = temp_store("audit-pull");
        let changes = vec![json!({
            "server_seq": 7, "entity_type": "audit", "entity_id": "aud9", "op": "upsert", "rev": 2,
            "payload": {
                "id": "aud9", "hospital_id": "h1", "code": "AUD-2026-0009",
                "title": "تدقيق من الخادم", "status": "completed", "score": 88,
                "findings_ar": "ملاحظتان", "audit_date": "2026-05-01"
            }
        })];
        assert_eq!(s.apply_pull(&changes, 7).unwrap(), 1);
        let rows = s.list_audits(Some("h1")).unwrap();
        assert_eq!(rows[0]["code"].as_str(), Some("AUD-2026-0009"));
        assert_eq!(rows[0]["status"].as_str(), Some("completed"));
        assert_eq!(rows[0]["score"].as_f64(), Some(88.0));
        assert_eq!(rows[0]["synced"].as_bool(), Some(true));
    }

    #[test]
    fn save_plan_queues_an_outbox_op_and_lists_locally() {
        let s = temp_store("plan");
        let out = s
            .save_plan("pln1", "h1", None, "خطة تحسين الانتظار", Some("تقليل الزمن"),
                       Some("٤٥ دقيقة"), Some("٢٠ دقيقة"), Some("مدير الجودة"),
                       Some("2026-06-01"), Some("2026-09-01"), "2026-03-01T09:00:00Z")
            .expect("save plan");
        assert_eq!(out["plan_id"].as_str(), Some("pln1"));

        let rows = s.list_plans(Some("h1")).expect("list");
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["status"].as_str(), Some("draft"));
        assert_eq!(rows[0]["target_ar"].as_str(), Some("٢٠ دقيقة"));

        let pending = s.pending(false).expect("pending");
        assert_eq!(pending[0].entity_type, "improvement_plan");
    }

    #[test]
    fn save_plan_action_queues_an_outbox_op_and_lists_locally() {
        let s = temp_store("plan-action");
        let out = s
            .save_plan_action("act1", "pln1", "خطوة تنفيذية", Some("مسؤول القسم"),
                              Some("2026-07-01"), Some("متابعة أسبوعية"), "2026-03-01T09:00:00Z")
            .expect("save plan action");
        assert_eq!(out["action_id"].as_str(), Some("act1"));

        let rows = s.list_plan_actions(Some("pln1")).expect("list");
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["plan_id"].as_str(), Some("pln1"));
        assert_eq!(rows[0]["status"].as_str(), Some("open"));

        let pending = s.pending(false).expect("pending");
        assert_eq!(pending[0].entity_type, "improvement_action");
    }

    #[test]
    fn ack_applied_marks_a_local_audit_and_plan_synced() {
        let s = temp_store("audit-plan-ack");
        let a = s.save_audit("aud1", "h1", None, "تدقيق", None, None, None, None, "t").unwrap();
        let p = s.save_plan("pln1", "h1", None, "خطة", None, None, None, None, None, None, "t").unwrap();
        s.outbox_ack(a["op_id"].as_str().unwrap(), "applied", Some(3), None).unwrap();
        s.outbox_ack(p["op_id"].as_str().unwrap(), "applied", Some(2), None).unwrap();
        assert_eq!(s.pending(false).unwrap().len(), 0);
        assert_eq!(s.list_audits(Some("h1")).unwrap()[0]["synced"].as_bool(), Some(true));
        assert_eq!(s.list_plans(Some("h1")).unwrap()[0]["rev"].as_i64(), Some(2));
    }

    #[test]
    fn data_survives_reopening_the_database() {
        // Simulates a power cut: the queued op must still be there after restart.
        let mut path = std::env::temp_dir();
        path.push(format!("yhq-test-reopen-{}.sqlite", uuid::Uuid::new_v4()));
        {
            let s = Store::open(path.clone()).unwrap();
            s.save_value("v1", "p1", "i1", None, Some(18.0), Some(20.0), None, "ratio",
                         Some(100.0), "higher_better", Some(90.0), None, None, None, "t").unwrap();
        }
        let reopened = Store::open(path.clone()).unwrap();
        assert_eq!(reopened.pending(false).unwrap().len(), 1);
        assert!(!reopened.status().unwrap().node_id.is_empty());
        let _ = std::fs::remove_file(path);
    }
}
