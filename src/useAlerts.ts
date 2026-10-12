import { useCallback, useEffect, useRef, useState } from 'react';
import type { AlertDefinition, AlertEvent, AlertServiceStatus } from './contracts';
import { api } from './api';

export function useAlerts() {
  const [alerts, setAlerts] = useState<AlertDefinition[]>([]);
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [status, setStatus] = useState<AlertServiceStatus | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState<AlertEvent | null>(null);
  const seen = useRef<Set<string> | null>(null);
  const request = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    try {
      const [definitions, history, state] = await Promise.all([
        api<AlertDefinition[]>('/alerts', { signal: controller.signal }),
        api<AlertEvent[]>('/alert-events', { signal: controller.signal }),
        api<AlertServiceStatus>('/alert-status', { signal: controller.signal }),
      ]);
      if (controller.signal.aborted) return;
      if (seen.current) {
        const latest = history.find(e => !seen.current!.has(e.id));
        if (latest) setNotice(latest);
      }
      seen.current = new Set(history.map(e => e.id));
      setAlerts(definitions); setEvents(history); setStatus(state); setError('');
    } catch (e) { if (!controller.signal.aborted) { setError(String(e)); setStatus(null); } }
  }, []);
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 5000);
    return () => { clearInterval(timer); request.current?.abort(); };
  }, [refresh]);
  return { alerts, events, status, error, notice, dismiss: () => setNotice(null), refresh };
}
