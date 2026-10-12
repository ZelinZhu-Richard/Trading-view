import { useModal } from './useModal';
import { useEffect, useRef, useState } from 'react';
import { Database, KeyRound, Search, X } from 'lucide-react';
import { api } from './api';
import type { Dataset, HistoryRequest, Instrument, ProviderCapabilities } from './contracts';

interface Props { onClose: () => void; onLoaded: (dataset: Dataset) => void }
export function ProviderDialog({ onClose, onLoaded }: Props) {
  const dialog = useModal();
  const [providers, setProviders] = useState<ProviderCapabilities[]>([]);
  const [provider, setProvider] = useState<HistoryRequest['provider']>('coinbase');
  const [key, setKey] = useState('');
  const [secret, setSecret] = useState('');
  const [query, setQuery] = useState('BTC-USD');
  const [results, setResults] = useState<Instrument[]>([]);
  const [instrument, setInstrument] = useState<Instrument | null>(null);
  const [interval, setInterval] = useState<HistoryRequest['interval']>('1d');
  const [start, setStart] = useState(new Date(Date.now() - 180 * 86400_000).toISOString().slice(0, 10));
  const [end, setEnd] = useState(new Date().toISOString().slice(0, 10));
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const cap = providers.find(p => p.id === provider);
  async function refresh() { setProviders(await api<ProviderCapabilities[]>('/providers')); }
  useEffect(() => { void refresh().catch(e => setError(String(e))); return () => controller.current?.abort(); }, []);
  async function search() {
    controller.current?.abort(); const request = new AbortController(); controller.current = request;
    setBusy(true); setError(''); setResults([]); setInstrument(null);
    try {
      const values = await api<Instrument[]>(`/providers/${provider}/instruments?query=${encodeURIComponent(query)}`, { signal: request.signal });
      if (!request.signal.aborted) { setResults(values); if (values.length === 1) setInstrument(values[0]); }
    } catch (e) { if (!request.signal.aborted) setError(String(e)); }
    finally { if (!request.signal.aborted) { setBusy(false); void refresh().catch(e => setError(String(e))); } }
  }
  async function configure() {
    setBusy(true); setError(''); setMessage('');
    try {
      await api(`/providers/${provider}/config`, { method: 'PUT', body: JSON.stringify({ api_key: key, secret_key: secret || null }) });
      setKey(''); setSecret(''); setMessage('Keys saved in local backend configuration.'); await refresh();
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function load() {
    if (!instrument) return;
    controller.current?.abort(); const request = new AbortController(); controller.current = request;
    setBusy(true); setError(''); setMessage('Fetching and validating history…');
    const body: HistoryRequest = { schema_version: 1, provider, instrument, interval,
      start: Date.parse(start + 'T00:00:00Z') / 1000, end: Date.parse(end + 'T00:00:00Z') / 1000 };
    try {
      const value = await api<Dataset>('/history', { method: 'POST', body: JSON.stringify(body), signal: request.signal });
      if (!request.signal.aborted) onLoaded(value);
    } catch (e) { if (!request.signal.aborted) { setError(String(e)); setMessage(''); } }
    finally { if (!request.signal.aborted) { setBusy(false); void refresh().catch(e => setError(String(e))); } }
  }
  return <dialog className="modal" ref={dialog} onCancel={onClose}>
    <header><div><span className="eyebrow">DOCUMENTED MARKET-DATA CONNECTIONS</span><h2>Connect a data source</h2></div><button className="icon-button" aria-label="Close data connections" onClick={onClose}><X size={18}/></button></header>
    <div className="modal-body"><div className="provider-tabs">{providers.map(p => <button key={p.id} className={provider === p.id ? 'selected' : ''} onClick={() => { controller.current?.abort(); setBusy(false); setProvider(p.id as typeof provider); setInstrument(null); setResults([]); setQuery(p.id === 'coinbase' ? 'BTC-USD' : p.id === 'alpaca' ? 'AAPL' : 'EUR/USD'); setInterval('1d'); setMessage(''); setError(''); setKey(''); setSecret(''); }}><Database size={16}/>{p.name}<small>{p.status.replace('-', ' ')}</small></button>)}</div>
      {cap && <><p className="muted">{cap.history}</p>{cap.limitations.map(l => <p className="provider-limit" key={l}>{l}</p>)}
      {cap.requires_keys && <details className="credential-form" open={cap.status === 'not-configured'}><summary><KeyRound size={14}/>Local API keys · {cap.status === 'not-configured' ? 'required' : 'configured'}</summary><div className="form-grid"><label>API key<input type="password" autoComplete="off" value={key} onChange={e => setKey(e.target.value)}/></label>{provider === 'alpaca' && <label>Secret key<input type="password" autoComplete="off" value={secret} onChange={e => setSecret(e.target.value)}/></label>}<button disabled={!key || busy || (provider === 'alpaca' && !secret)} onClick={() => void configure()}>Save keys locally</button></div></details>}
      <form className="provider-search" onSubmit={e => { e.preventDefault(); void search(); }}><input aria-label="Provider instrument search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search symbol or instrument"/><button disabled={busy || (cap.requires_keys && cap.status === 'not-configured')}><Search size={15}/>Search</button></form>
      {provider === 'alpha-vantage' && <p className="small-note">The search list contains common currency pairs. Availability is checked when requesting history.</p>}
      <div className="provider-results">{results.map(i => <button className={instrument?.id === i.id ? 'selected' : ''} key={i.id} onClick={() => setInstrument(i)}><span><b>{i.symbol}</b><small>{i.name}</small></span><span>{i.exchange} · {i.quote_currency}</span></button>)}</div>
      <div className="form-grid"><label>Start date · UTC<input type="date" value={start} onChange={e => setStart(e.target.value)}/></label><label>End date · UTC (exclusive)<input type="date" value={end} onChange={e => setEnd(e.target.value)}/></label><label>History interval<select aria-label="Provider history interval" value={interval} onChange={e => setInterval(e.target.value as typeof interval)}>{cap.intervals.map(i => <option key={i}>{i}</option>)}</select></label></div></>}
      {message && <p className="notice">{message}</p>}{error && <p role="alert" className="error">{error}</p>}
    </div><footer><button onClick={onClose}>Close</button>{busy ? <button onClick={() => { controller.current?.abort(); setBusy(false); setMessage('Request cancelled. Existing datasets were preserved.'); }}>Cancel request</button> : <button className="primary" disabled={!instrument || !start || !end || start >= end} onClick={() => void load()}>Load market history</button>}</footer>
  </dialog>;
}
