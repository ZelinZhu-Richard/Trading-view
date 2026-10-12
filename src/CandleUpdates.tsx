import { useEffect, useState } from 'react';
import type { CandleStatus } from './contracts';
import { api } from './api';

export function CandleUpdates() {
  const [status, setStatus] = useState<{ running: boolean; error: string | null; series: CandleStatus[] } | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try { const next = await api<typeof status>('/candles', { signal: controller.signal }); if (!controller.signal.aborted) { setStatus(next); setError(''); } }
      catch (e) { if (!controller.signal.aborted) setError(String(e)); }
      finally { if (!controller.signal.aborted) timer = setTimeout(poll, 3000); }
    }
    void poll(); return () => { controller.abort(); clearTimeout(timer); };
  }, []);
  return <details className="candle-updates"><summary>Provider candle updates · {error ? 'disconnected' : status?.running ? 'local service running' : 'checking service'}</summary><p>Visible charts with Follow candles, enabled alerts, and paper accounts share completed-candle checks. Coinbase/Alpaca check every 30 seconds; daily forex checks once per day. Quotes are separate.</p>{(error || status?.error) && <p role="alert">{error || status?.error}</p>}{status?.series.map(item => <p key={item.series_id}><b>{item.dataset.instrument.symbol} · {item.dataset.interval}</b> · {item.active ? item.status : 'paused'} · {item.message} {item.last_success && <>Last successful check: {new Date(item.last_success).toLocaleString()}. </>}{item.revised_history && <strong>Completed history was revised. Review alerts and paper accounts.</strong>}<button disabled={!item.active} onClick={async () => { try { await api(`/candles/${item.dataset.id}/retry`, { method: 'POST' }); setError(''); } catch (e) { setError(String(e)); } }}>Retry check</button></p>)}</details>;
}
