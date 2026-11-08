// React glue for the sync engine: exposes local status, runs sync on a timer and
// whenever the connection returns, and lets any page trigger a sync on demand.

import { useCallback, useEffect, useState } from "react";
import { desktop, isDesktop, type LocalStatus } from "./desktop";
import { runSync, type SyncOutcome } from "./sync";

export interface SyncController {
  desktop: boolean;
  status: LocalStatus | null;
  busy: boolean;
  online: boolean;
  lastOutcome: SyncOutcome | null;
  refresh: () => Promise<void>;
  syncNow: () => Promise<void>;
}

export function useSync(): SyncController {
  const [status, setStatus] = useState<LocalStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [online, setOnline] = useState<boolean>(navigator.onLine);
  const [lastOutcome, setLastOutcome] = useState<SyncOutcome | null>(null);
  const isDesk = isDesktop();

  const refresh = useCallback(async () => {
    if (!isDesk) return;
    setStatus(await desktop.localStatus());
  }, [isDesk]);

  const syncNow = useCallback(async () => {
    if (!isDesk) return;
    setBusy(true);
    try {
      const outcome = await runSync();
      setLastOutcome(outcome);
      await refresh();
    } finally {
      setBusy(false);
    }
  }, [isDesk, refresh]);

  useEffect(() => {
    const goOnline = () => {
      setOnline(true);
      void syncNow();
    };
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, [syncNow]);

  useEffect(() => {
    if (!isDesk) return;
    void syncNow();
    const timer = window.setInterval(() => void syncNow(), 60_000);
    return () => window.clearInterval(timer);
  }, [isDesk, syncNow]);

  return { desktop: isDesk, status, busy, online, lastOutcome, refresh, syncNow };
}
