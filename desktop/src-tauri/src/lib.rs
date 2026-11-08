// Desktop shell for the national quality system.
//
// v0.2 was a thin shell around the web UI. v0.6 adds the offline store: the web
// UI calls these commands to persist edits locally (with an outbox) and to
// record what the server returns. Network calls stay in the web UI, which holds
// the session token; this crate owns durable local state only.

mod store;

use std::path::PathBuf;
use std::sync::Mutex;

use serde_json::Value;
use store::{now_iso, SaveValueInput, Store};
use tauri::{Manager, State};

/// Version of the desktop application shell.
#[tauri::command]
fn app_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

/// Open (once) the local database that lives in the app data directory.
fn ensure_store(state: &State<'_, Mutex<Option<Store>>>, app: &tauri::AppHandle) -> Result<(), String> {
    let mut guard = state.lock().map_err(|_| "state lock poisoned".to_string())?;
    if guard.is_some() {
        return Ok(());
    }
    let dir: PathBuf = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("no app data dir: {e}"))?;
    std::fs::create_dir_all(&dir).map_err(|e| format!("create data dir: {e}"))?;
    let db_path = dir.join("yhq-offline.sqlite");
    *guard = Some(Store::open(db_path)?);
    Ok(())
}

fn with_store<T>(
    state: &State<'_, Mutex<Option<Store>>>,
    app: &tauri::AppHandle,
    f: impl FnOnce(&Store) -> Result<T, String>,
) -> Result<T, String> {
    ensure_store(state, app)?;
    let guard = state.lock().map_err(|_| "state lock poisoned".to_string())?;
    let s = guard.as_ref().ok_or_else(|| "store not initialised".to_string())?;
    f(s)
}

#[tauri::command]
fn local_status(state: State<'_, Mutex<Option<Store>>>, app: tauri::AppHandle) -> Result<Value, String> {
    let status = with_store(&state, &app, |s| s.status())?;
    serde_json::to_value(status).map_err(|e| e.to_string())
}

#[tauri::command]
fn set_hospital(
    hospital_id: String,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<(), String> {
    with_store(&state, &app, |s| s.set_hospital(&hospital_id))
}

#[tauri::command]
fn set_cursor(seq: i64, state: State<'_, Mutex<Option<Store>>>, app: tauri::AppHandle) -> Result<(), String> {
    with_store(&state, &app, |s| s.set_cursor(seq))
}

#[tauri::command]
fn mark_synced(at: Option<String>, state: State<'_, Mutex<Option<Store>>>, app: tauri::AppHandle) -> Result<(), String> {
    let at = at.unwrap_or_else(now_iso);
    with_store(&state, &app, |s| s.mark_synced_now(&at))
}

#[tauri::command]
fn save_value(
    input: SaveValueInput,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<Value, String> {
    let value_id = input
        .value_id
        .clone()
        .unwrap_or_else(|| format!("val-{}", uuid::Uuid::new_v4()));
    let at = now_iso();
    with_store(&state, &app, |s| {
        s.save_value(
            &value_id,
            &input.period_id,
            &input.indicator_id,
            input.department_id.as_deref(),
            input.numerator,
            input.denominator,
            input.entered_value,
            &input.computation,
            input.multiplier,
            &input.direction,
            input.target_value,
            input.acceptable_min,
            input.acceptable_max,
            input.note.as_deref(),
            &at,
        )
    })
}

#[tauri::command]
fn list_values(
    period_id: String,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<Vec<Value>, String> {
    with_store(&state, &app, |s| s.list_values(&period_id))
}

#[tauri::command]
#[allow(clippy::too_many_arguments)]
fn save_incident(
    incident_id: String,
    hospital_id: String,
    department_id: Option<String>,
    title: String,
    description: Option<String>,
    incident_type: String,
    severity: String,
    patient_harm: String,
    occurred_at: Option<String>,
    is_anonymous: Option<bool>,
    immediate_action: Option<String>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<Value, String> {
    let at = now_iso();
    with_store(&state, &app, |s| {
        s.save_incident(
            &incident_id,
            &hospital_id,
            department_id.as_deref(),
            &title,
            description.as_deref(),
            &incident_type,
            &severity,
            &patient_harm,
            occurred_at.as_deref(),
            is_anonymous.unwrap_or(false),
            immediate_action.as_deref(),
            &at,
        )
    })
}

#[tauri::command]
fn list_incidents(
    hospital_id: Option<String>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<Vec<Value>, String> {
    with_store(&state, &app, |s| s.list_incidents(hospital_id.as_deref()))
}

#[tauri::command]
#[allow(clippy::too_many_arguments)]
fn save_capa(
    capa_id: String,
    hospital_id: String,
    department_id: Option<String>,
    incident_id: Option<String>,
    kind: String,
    title: String,
    description_ar: Option<String>,
    owner_name_ar: Option<String>,
    due_date: Option<String>,
    priority: String,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<Value, String> {
    let at = now_iso();
    with_store(&state, &app, |s| {
        s.save_capa(
            &capa_id,
            &hospital_id,
            department_id.as_deref(),
            incident_id.as_deref(),
            &kind,
            &title,
            description_ar.as_deref(),
            owner_name_ar.as_deref(),
            due_date.as_deref(),
            &priority,
            &at,
        )
    })
}

#[tauri::command]
fn list_capa(
    hospital_id: Option<String>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<Vec<Value>, String> {
    with_store(&state, &app, |s| s.list_capa(hospital_id.as_deref()))
}

#[tauri::command]
#[allow(clippy::too_many_arguments)]
fn save_risk(
    risk_id: String,
    hospital_id: String,
    department_id: Option<String>,
    title: String,
    description_ar: Option<String>,
    category: String,
    likelihood: i64,
    impact: i64,
    mitigation_ar: Option<String>,
    owner_name_ar: Option<String>,
    review_date: Option<String>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<Value, String> {
    let at = now_iso();
    with_store(&state, &app, |s| {
        s.save_risk(
            &risk_id,
            &hospital_id,
            department_id.as_deref(),
            &title,
            description_ar.as_deref(),
            &category,
            likelihood,
            impact,
            mitigation_ar.as_deref(),
            owner_name_ar.as_deref(),
            review_date.as_deref(),
            &at,
        )
    })
}

#[tauri::command]
fn list_risks(
    hospital_id: Option<String>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<Vec<Value>, String> {
    with_store(&state, &app, |s| s.list_risks(hospital_id.as_deref()))
}

#[tauri::command]
#[allow(clippy::too_many_arguments)]
fn save_audit(
    audit_id: String,
    hospital_id: String,
    department_id: Option<String>,
    title: String,
    standard_ar: Option<String>,
    scope_ar: Option<String>,
    auditor_name_ar: Option<String>,
    audit_date: Option<String>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<Value, String> {
    let at = now_iso();
    with_store(&state, &app, |s| {
        s.save_audit(
            &audit_id,
            &hospital_id,
            department_id.as_deref(),
            &title,
            standard_ar.as_deref(),
            scope_ar.as_deref(),
            auditor_name_ar.as_deref(),
            audit_date.as_deref(),
            &at,
        )
    })
}

#[tauri::command]
fn list_audits(
    hospital_id: Option<String>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<Vec<Value>, String> {
    with_store(&state, &app, |s| s.list_audits(hospital_id.as_deref()))
}

#[tauri::command]
#[allow(clippy::too_many_arguments)]
fn save_plan(
    plan_id: String,
    hospital_id: String,
    department_id: Option<String>,
    title: String,
    objective_ar: Option<String>,
    baseline_ar: Option<String>,
    target_ar: Option<String>,
    owner_name_ar: Option<String>,
    start_date: Option<String>,
    due_date: Option<String>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<Value, String> {
    let at = now_iso();
    with_store(&state, &app, |s| {
        s.save_plan(
            &plan_id,
            &hospital_id,
            department_id.as_deref(),
            &title,
            objective_ar.as_deref(),
            baseline_ar.as_deref(),
            target_ar.as_deref(),
            owner_name_ar.as_deref(),
            start_date.as_deref(),
            due_date.as_deref(),
            &at,
        )
    })
}

#[tauri::command]
fn list_plans(
    hospital_id: Option<String>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<Vec<Value>, String> {
    with_store(&state, &app, |s| s.list_plans(hospital_id.as_deref()))
}

#[tauri::command]
#[allow(clippy::too_many_arguments)]
fn save_plan_action(
    action_id: String,
    plan_id: String,
    title: String,
    owner_name_ar: Option<String>,
    due_date: Option<String>,
    note_ar: Option<String>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<Value, String> {
    let at = now_iso();
    with_store(&state, &app, |s| {
        s.save_plan_action(
            &action_id,
            &plan_id,
            &title,
            owner_name_ar.as_deref(),
            due_date.as_deref(),
            note_ar.as_deref(),
            &at,
        )
    })
}

#[tauri::command]
fn list_plan_actions(
    plan_id: Option<String>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<Vec<Value>, String> {
    with_store(&state, &app, |s| s.list_plan_actions(plan_id.as_deref()))
}

#[tauri::command]
#[allow(clippy::too_many_arguments)]
fn create_period(
    period_id: String,
    hospital_id: String,
    period_type: String,
    year: i64,
    month: Option<i64>,
    quarter: Option<i64>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<Value, String> {
    let at = now_iso();
    with_store(&state, &app, |s| {
        s.create_period(&period_id, &hospital_id, &period_type, year, month, quarter, &at)
    })
}

#[tauri::command]
fn list_periods(
    hospital_id: Option<String>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<Vec<Value>, String> {
    with_store(&state, &app, |s| s.list_periods(hospital_id.as_deref()))
}

#[tauri::command]
fn cache_departments(
    departments: Vec<Value>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<usize, String> {
    with_store(&state, &app, |s| s.cache_departments(&departments))
}

#[tauri::command]
fn list_departments(state: State<'_, Mutex<Option<Store>>>, app: tauri::AppHandle) -> Result<Vec<Value>, String> {
    with_store(&state, &app, |s| s.list_departments())
}

#[tauri::command]
fn cache_hospitals(
    hospitals: Vec<Value>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<usize, String> {
    with_store(&state, &app, |s| s.cache_hospitals(&hospitals))
}

#[tauri::command]
fn list_hospitals(state: State<'_, Mutex<Option<Store>>>, app: tauri::AppHandle) -> Result<Vec<Value>, String> {
    with_store(&state, &app, |s| s.list_hospitals())
}

#[tauri::command]
fn cache_assignments(
    assignments: Vec<Value>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<usize, String> {
    with_store(&state, &app, |s| s.cache_assignments(&assignments))
}

#[tauri::command]
fn list_assignments(state: State<'_, Mutex<Option<Store>>>, app: tauri::AppHandle) -> Result<Vec<Value>, String> {
    with_store(&state, &app, |s| s.list_assignments())
}

#[tauri::command]
fn pending_ops(
    include_failed: Option<bool>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<Value, String> {
    let ops = with_store(&state, &app, |s| s.pending(include_failed.unwrap_or(false)))?;
    serde_json::to_value(ops).map_err(|e| e.to_string())
}

#[tauri::command]
fn outbox_ack(
    op_id: String,
    status: String,
    new_rev: Option<i64>,
    error: Option<String>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<(), String> {
    with_store(&state, &app, |s| s.outbox_ack(&op_id, &status, new_rev, error.as_deref()))
}

#[tauri::command]
fn bump_attempts(
    op_id: String,
    error: String,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<(), String> {
    with_store(&state, &app, |s| s.bump_attempts(&op_id, &error))
}

#[tauri::command]
fn apply_pull(
    changes: Vec<Value>,
    to_seq: i64,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<i64, String> {
    with_store(&state, &app, |s| s.apply_pull(&changes, to_seq))
}

#[tauri::command]
fn cache_library(
    indicators: Vec<Value>,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<usize, String> {
    with_store(&state, &app, |s| s.cache_library(&indicators))
}

#[tauri::command]
fn local_library(state: State<'_, Mutex<Option<Store>>>, app: tauri::AppHandle) -> Result<Vec<Value>, String> {
    with_store(&state, &app, |s| s.library())
}

#[tauri::command]
fn record_conflict(
    op_id: String,
    entity_type: String,
    entity_id: String,
    local_payload: Value,
    server_payload: Value,
    state: State<'_, Mutex<Option<Store>>>,
    app: tauri::AppHandle,
) -> Result<(), String> {
    let at = now_iso();
    with_store(&state, &app, |s| {
        s.record_conflict(&op_id, &entity_type, &entity_id, &local_payload, &server_payload, &at)
    })
}

#[tauri::command]
fn list_conflicts(state: State<'_, Mutex<Option<Store>>>, app: tauri::AppHandle) -> Result<Vec<Value>, String> {
    with_store(&state, &app, |s| s.conflicts())
}

#[tauri::command]
fn export_backup(state: State<'_, Mutex<Option<Store>>>, app: tauri::AppHandle) -> Result<Value, String> {
    with_store(&state, &app, |s| s.export_backup())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(Mutex::new(None::<Store>))
        .invoke_handler(tauri::generate_handler![
            app_version,
            local_status,
            set_hospital,
            set_cursor,
            mark_synced,
            save_value,
            list_values,
            save_incident,
            list_incidents,
            save_capa,
            list_capa,
            save_risk,
            list_risks,
            save_audit,
            list_audits,
            save_plan,
            list_plans,
            save_plan_action,
            list_plan_actions,
            create_period,
            list_periods,
            cache_departments,
            list_departments,
            cache_hospitals,
            list_hospitals,
            cache_assignments,
            list_assignments,
            pending_ops,
            outbox_ack,
            bump_attempts,
            apply_pull,
            cache_library,
            local_library,
            record_conflict,
            list_conflicts,
            export_backup,
        ])
        .run(tauri::generate_context!())
        .expect("error while running the desktop application");
}
