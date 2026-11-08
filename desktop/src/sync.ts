// Sync engine (v0.6) — the client side of docs/14.
//
// Flow: push the local outbox (each op has a unique op_id, so a retry never
// duplicates), then pull everything the server changed since our cursor. If a
// push reports a conflict, the server's version wins and we record it locally.
//
// The engine never touches the network itself: it takes the API client, so it
// stays testable and the UI decides when to run it (on load, on a timer, or when
// the connection returns).

import { api } from "./api";
import { desktop, isDesktop, type PendingOp } from "./desktop";

export interface SyncOutcome {
  ok: boolean;
  pushed: number;
  applied: number;
  conflicts: number;
  rejected: number;
  pulled: number;
  message: string;
  offline: boolean;
}

const EMPTY: SyncOutcome = {
  ok: false,
  pushed: 0,
  applied: 0,
  conflicts: 0,
  rejected: 0,
  pulled: 0,
  message: "",
  offline: false,
};

function isOfflineError(e: unknown): boolean {
  // A fetch failure (no network) throws TypeError, not an ApiError.
  return e instanceof TypeError || (e instanceof Error && /fetch|network/i.test(e.message));
}

/**
 * Run one full sync cycle. Safe to call repeatedly and while offline: it returns
 * a result describing what happened rather than throwing.
 */
export async function runSync(): Promise<SyncOutcome> {
  if (!isDesktop()) {
    return { ...EMPTY, message: "المزامنة متاحة في تطبيق سطح المكتب فقط." };
  }
  const status = await desktop.localStatus();
  if (!status) {
    return { ...EMPTY, message: "تعذّر الوصول إلى المخزن المحلي." };
  }

  const outcome: SyncOutcome = { ...EMPTY, ok: true, message: "" };
  try {
    // ---- push ----
    const pending: PendingOp[] = (await desktop.pendingOps(false)) ?? [];
    if (pending.length > 0) {
      const batch = `batch-${Date.now()}`;
      const resp = await api.syncPush({
        node_id: status.node_id,
        hospital_id: status.hospital_id,
        batch_id: batch,
        operations: pending.map((p) => ({
          op_id: p.op_id,
          entity_type: p.entity_type,
          entity_id: p.entity_id,
          op: p.op,
          base_rev: p.base_rev,
          payload: p.payload,
        })),
      });
      outcome.pushed = pending.length;
      for (const result of resp.results) {
        if (result.status === "applied") {
          outcome.applied += 1;
          await desktop.outboxAck(result.op_id, "applied", result.new_rev ?? null, null);
        } else if (result.status === "conflict") {
          outcome.conflicts += 1;
          const op = pending.find((p) => p.op_id === result.op_id);
          await desktop.recordConflict(
            result.op_id,
            op?.entity_type ?? "unknown",
            op?.entity_id ?? "",
            op?.payload ?? {},
            result.server_payload ?? {},
          );
        } else {
          outcome.rejected += 1;
          await desktop.outboxAck(result.op_id, "rejected", null, result.reason ?? "rejected");
        }
      }
    }

    // ---- pull ----
    let cursor = status.cursor;
    let hasMore = true;
    let guard = 0;
    while (hasMore && guard < 50) {
      const pulled = await api.syncPull(cursor, status.node_id);
      if (pulled.changes.length > 0) {
        await desktop.applyPull(pulled.changes, pulled.to_seq);
        outcome.pulled += pulled.changes.length;
      }
      cursor = pulled.to_seq;
      hasMore = pulled.has_more;
      guard += 1;
    }
    if (status.cursor === 0) {
      // First run: cache the national library, departments and assignments so the
      // entry form works fully offline next time.
      const boot = await api.syncBootstrap(status.node_id, status.hospital_id ?? undefined);
      await desktop.cacheLibrary(boot.indicators);
      await desktop.cacheDepartments(boot.departments);
      await desktop.cacheAssignments(boot.assignments);
    }
    await desktop.setCursor(cursor);
    await desktop.markSynced(new Date().toISOString());
    outcome.message = `تمت المزامنة: أُرسل ${outcome.applied}، استُقبل ${outcome.pulled}.`;
  } catch (e) {
    if (isOfflineError(e)) {
      outcome.offline = true;
      outcome.ok = false;
      outcome.message = "لا يوجد اتصال بالخادم؛ سيبقى العمل محلياً ويُرسَل تلقائياً لاحقاً.";
    } else {
      outcome.ok = false;
      outcome.message = e instanceof Error ? e.message : "تعذّرت المزامنة.";
    }
  }
  return outcome;
}
