import { useModal } from './useModal';
import { useState } from 'react';
import { Upload, ArrowRight, Check, X } from 'lucide-react';
import type { Dataset, ImportPreview, ImportRequest } from './contracts';
import { api, formatPrice } from './api';
import { parseCsv } from './csv';

interface Props { onClose: () => void; onImported: (value: Dataset) => void }

export function ImportDialog({ onClose, onImported }: Props) {
  const dialog = useModal();
  const [filename, setFilename] = useState('');
  const [csv, setCsv] = useState('');
  const [columns, setColumns] = useState<string[]>([]);
  const [mapping, setMapping] = useState<Record<string, string>>({ timestamp: 'timestamp', open: 'open', high: 'high', low: 'low', close: 'close', volume: 'volume' });
  const [symbol, setSymbol] = useState('');
  const [currency, setCurrency] = useState('USD');
  const [exchange, setExchange] = useState('CUSTOM');
  const [zone, setZone] = useState('');
  const [calendar, setCalendar] = useState('24/7');
  const [interval, setInterval] = useState<ImportRequest['interval']>('1d');
  const [adjustment, setAdjustment] = useState<ImportRequest['adjustment']>('raw');
  const [conflict, setConflict] = useState<ImportRequest['conflict_policy']>('reject');
  const [format, setFormat] = useState('');
  const [tick, setTick] = useState('0.01');
  const [quantityStep, setQuantityStep] = useState('1');
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function inspect() {
    setBusy(true); setError('');
    const request: ImportRequest = { schema_version: 1, csv_text: csv, interval, timezone: zone || null,
      timestamp_format: format || null, columns: mapping, adjustment, conflict_policy: conflict,
      instrument: { schema_version: 1, id: `CSV:${exchange}:${symbol}`, symbol, name: symbol,
        exchange, asset_class: 'other', quote_currency: currency, base_currency: null,
        timezone: zone || 'UTC', calendar, session: 'regular', price_tick: tick, quantity_step: quantityStep, provider_symbols: {} } };
    try { setPreview(await api<ImportPreview>('/imports/preview', { method: 'POST', body: JSON.stringify(request) })); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  async function commit() {
    setBusy(true); setError('');
    try { const value = await api<Dataset>('/imports/commit', { method: 'POST', body: JSON.stringify({ token: preview?.token }) }); onImported(value); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  return <dialog className="modal import-modal" ref={dialog} onCancel={onClose}>
    <header><div><span className="eyebrow">YOUR DATA, YOUR WORKSPACE</span><h2>Import market data</h2></div><button className="icon-button" aria-label="Close import" onClick={onClose}><X size={19}/></button></header>
    <div className="modal-body">
      {preview ? <>
        <div className="import-summary"><strong>{preview.valid_rows.toLocaleString()} valid bars</strong><span>{preview.invalid_rows} errors</span><span>{preview.exact_duplicates} exact duplicates removed</span><span>{preview.conflicting_duplicates} conflicts</span></div>
        <p className="muted">{filename} · {symbol} · {currency} · {interval} · {zone || 'UTC offsets from file'}</p>
        {preview.warnings.map(w => <p className="notice" key={w}>{w}</p>)}
        {preview.errors.length > 0 && <div className="error-list" role="alert">{preview.errors.slice(0, 100).map((e, i) => <p key={i}>Row {e.row}: {e.message}</p>)}{preview.errors.length > 100 && <p>{preview.errors.length - 100} additional row errors.</p>}</div>}
        <div className="table-wrap"><table><caption>First {preview.preview.length} normalized bars · UTC</caption><thead><tr><th>Time</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Volume</th></tr></thead><tbody>{preview.preview.map(b => <tr key={b.start}><td>{new Date(b.start * 1000).toISOString().slice(0, 16).replace('T', ' ')}</td>{[b.open, b.high, b.low, b.close].map((v, i) => <td key={i}>{formatPrice(v)}</td>)}<td>{b.volume?.toLocaleString() ?? 'Missing'}</td></tr>)}</tbody></table></div>
      </> : <>
        <label className="file-drop"><Upload size={26}/><strong>{filename || 'Choose a CSV file'}</strong><span>OHLC bars, with optional volume</span><input aria-label="CSV file" type="file" accept=".csv,text/csv" onChange={async e => {
          const file = e.target.files?.[0]; if (!file) return;
          try {
            if (file.size > 30_000_000) throw new Error('CSV file exceeds the 30 MB import limit.');
            const content = (await file.text()).replace(/^\uFEFF/, '');
            const header = parseCsv(content, 1)[0] ?? [];
            setCsv(content); setFilename(file.name); setColumns(header);
            setMapping(Object.fromEntries(Object.keys(mapping).map(key => [key, header.find(c => c.toLowerCase() === key) ?? (key === 'timestamp' ? header[0] : '')])));
            setError('');
          } catch (error) { setCsv(''); setColumns([]); setError(String(error)); }
        }}/></label>
        {columns.length > 0 && <><h3>Map columns</h3><div className="form-grid columns-grid">{Object.keys(mapping).map(key => <label key={key}>{key}<select value={mapping[key]} onChange={e => setMapping({ ...mapping, [key]: e.target.value })}><option value="">{key === 'volume' ? 'Not provided' : 'Choose column'}</option>{columns.map((c, i) => <option key={i}>{c}</option>)}</select></label>)}</div></>}
        <h3>Instrument & session</h3><div className="form-grid">
          <label>Symbol<input value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} placeholder="e.g. 600519"/></label>
          <label>Venue<input value={exchange} onChange={e => setExchange(e.target.value.toUpperCase())}/></label>
          <label>Currency<input value={currency} onChange={e => setCurrency(e.target.value.toUpperCase())}/></label>
          <label>Interval<select value={interval} onChange={e => setInterval(e.target.value as typeof interval)}>{['1m', '5m', '15m', '30m', '1h', '4h', '1d'].map(v => <option key={v}>{v}</option>)}</select></label>
          <label>Exchange calendar<select value={calendar} onChange={e => { setCalendar(e.target.value); if (e.target.value === 'XNYS') setZone('America/New_York'); if (e.target.value === 'XSHG') setZone('Asia/Shanghai'); }}><option value="24/7">Every day · 24 hours</option><option value="24/5">Weekdays · 24 hours</option><option value="XNYS">US equities · NYSE calendar</option><option value="XSHG">China equities · Shanghai</option></select></label>
          <label>Timestamp timezone<input aria-label="Timestamp timezone" value={zone} onChange={e => setZone(e.target.value)} list="zones" placeholder="Required without UTC offset"/><datalist id="zones"><option>UTC</option><option>America/New_York</option><option>Asia/Shanghai</option><option>Europe/London</option></datalist></label>
          <label>Timestamp format<input value={format} onChange={e => setFormat(e.target.value)} placeholder="Auto or %Y-%m-%d %H:%M"/></label>
          <label>Price adjustment<select value={adjustment} onChange={e => setAdjustment(e.target.value as typeof adjustment)}>{['raw', 'split', 'total-return', 'unknown'].map(v => <option key={v}>{v}</option>)}</select></label>
          <label>Price tick<input value={tick} onChange={e => setTick(e.target.value)} type="number" min="0.00000001" step="any"/></label>
          <label>Quantity step<input value={quantityStep} onChange={e => setQuantityStep(e.target.value)} type="number" min="0.00000001" step="any"/></label>
          <label>Conflicting duplicates<select value={conflict} onChange={e => setConflict(e.target.value as typeof conflict)}><option value="reject">Reject and report</option><option value="first">Keep first row</option><option value="last">Keep last row</option></select></label>
        </div>
      </>}
      {error && <p className="error" role="alert">{error}</p>}
    </div>
    <footer><button onClick={() => preview ? setPreview(null) : onClose()}>{preview ? 'Back to mapping' : 'Cancel'}</button><button className="primary" disabled={busy || (preview ? !preview.can_commit : !csv || !symbol)} onClick={() => void (preview ? commit() : inspect())}>{busy ? 'Working…' : preview ? 'Import dataset' : 'Review import'}{preview ? <Check size={16}/> : <ArrowRight size={16}/>}</button></footer>
  </dialog>;
}
