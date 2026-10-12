import { useEffect, useRef, useState } from 'react';
import { createChart, LineSeries, type Time } from 'lightweight-charts';
import { Download, Square } from 'lucide-react';
import type { ResearchJob, ResearchResult } from './contracts';
import { api, download } from './api';

const terminal = new Set(['completed', 'failed', 'cancelled', 'interrupted']);
const money = (value: string | number | null | undefined) => value == null ? 'Unavailable' : Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
function valueText(value: unknown): string {
  if (value == null) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}
function ResultsTable({ rows }: { rows: object[] }) {
  const [page, setPage] = useState(0);
  const columns = rows.length ? Object.keys(rows[0]).filter(key => key !== 'schema_version') : [];
  return <div className="research-table"><div className="table-wrap"><table><thead><tr>{columns.map(key => <th key={key}>{key.replaceAll('_', ' ')}</th>)}</tr></thead><tbody>{rows.slice(page*100, page*100+100).map((row, index) => <tr key={index}>{columns.map(key => <td key={key} title={valueText((row as Record<string, unknown>)[key])}>{valueText((row as Record<string, unknown>)[key])}</td>)}</tr>)}</tbody></table>{!rows.length && <p className="panel-empty">No records for this run.</p>}</div><div className="table-pagination"><button disabled={!page} onClick={() => setPage(page-1)}>Previous</button><span>{rows.length.toLocaleString()} records · page {page+1} of {Math.max(1, Math.ceil(rows.length/100))}</span><button disabled={(page+1)*100 >= rows.length} onClick={() => setPage(page+1)}>Next</button></div></div>;
}
function EquityChart({ result, theme }: { result: ResearchResult; theme: 'dark' | 'light' }) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!host.current) return;
    const chart = createChart(host.current, { autoSize: true, layout: { textColor: theme === 'dark' ? '#a6b7c7' : '#43576b', background: { color: theme === 'dark' ? '#101820' : '#fff' } }, grid: { vertLines: { visible: false }, horzLines: { color: theme === 'dark' ? '#1c2a36' : '#e6ecf1' } }, timeScale: { timeVisible: true }, localization: { locale: 'en-US' } });
    const equity = chart.addSeries(LineSeries, { color: '#68b8ea', lineWidth: 2, title: `Equity · ${result.settings.reporting_currency}` });
    equity.setData(result.equity.map(point => point.equity == null ? { time: point.time as Time } : { time: point.time as Time, value: Number(point.equity) }));
    const drawdown = chart.addSeries(LineSeries, { color: '#e5a576', lineWidth: 1, title: 'Drawdown %' }, 1);
    drawdown.setData(result.equity.map(point => point.drawdown == null ? { time: point.time as Time } : { time: point.time as Time, value: point.drawdown*100 }));
    chart.panes()[0]?.setStretchFactor(3); chart.panes()[1]?.setStretchFactor(1); chart.timeScale().fitContent();
    return () => chart.remove();
  }, [result, theme]);
  return <div className="research-equity" ref={host} aria-label="Portfolio equity and drawdown chart"/>;
}

export function ResearchPanel({ selectedId, onSelect, theme }: { selectedId: string | null; onSelect: (id: string) => void; theme: 'dark' | 'light' }) {
  const [jobs, setJobs] = useState<ResearchJob[]>([]), [result, setResult] = useState<ResearchResult | null>(null);
  const [error, setError] = useState(''), [output, setOutput] = useState<{ stdout: string; stderr: string; logs?: Array<Record<string, unknown>> }>({ stdout: '', stderr: '' });
  const [tab, setTab] = useState('overview'), [snapshot, setSnapshot] = useState<unknown>(null);
  const [comparison, setComparison] = useState<string[]>([]), [compared, setCompared] = useState<Record<string, ResearchResult>>({});
  const [cancelling, setCancelling] = useState(false);
  const job = jobs.find(value => value.id === selectedId);
  useEffect(() => {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try { const values = await api<ResearchJob[]>('/research', { signal: controller.signal }); if (!controller.signal.aborted) { setJobs(values); if (!selectedId && values.length) onSelect(values[0].id); } }
      catch (e) { if (!controller.signal.aborted) setError(String(e)); }
      finally { if (!controller.signal.aborted) timer = setTimeout(poll, 1500); }
    };
    void poll(); return () => { controller.abort(); clearTimeout(timer); };
  }, [selectedId, onSelect]);
  useEffect(() => {
    setResult(null); setSnapshot(null); setOutput({ stdout: '', stderr: '' }); setCancelling(false); setError('');
  }, [selectedId]);
  useEffect(() => {
    if (!job) return;
    const controller = new AbortController();
    api<{ stdout: string; stderr: string; logs: Array<Record<string, unknown>> }>(`/research/${job.id}/output`, { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setOutput(value); }).catch(e => { if (!controller.signal.aborted) setError(String(e)); });
    if (job.status === 'completed') api<ResearchResult>(`/research/${job.id}/result`, { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setResult(value); }).catch(e => { if (!controller.signal.aborted) setError(String(e)); });
    return () => controller.abort();
  }, [job?.id, job?.revision]);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all(comparison.map(async id => [id, await api<ResearchResult>(`/research/${id}/result`, { signal: controller.signal })] as const)).then(values => { if (!controller.signal.aborted) setCompared(Object.fromEntries(values)); }).catch(e => { if (!controller.signal.aborted) setError(String(e)); });
    return () => controller.abort();
  }, [comparison]);
  async function exportTable(table: string) {
    if (!job) return;
    try {
      const response = await fetch(`/api/research/${job.id}/export/${table}`);
      if (!response.ok) throw new Error((await response.json()).detail);
      download(`${job.name}-${table}.${table === 'json' ? 'json' : 'csv'}`, await response.blob());
    } catch (e) { setError(String(e)); }
  }
  const tables: Record<string, object[]> = result ? { orders: result.orders, fills: result.fills, trades: result.trades,
    positions: result.final_portfolio.positions, contributions: result.contributions, equity: result.equity, plots: result.plots } : {};
  return <section className="research-panel" aria-label="Research results"><aside className="research-runs"><h3>Saved runs</h3>{jobs.map(value => <div className={value.id === selectedId ? 'active' : ''} key={value.id}><button onClick={() => { onSelect(value.id); setTab('overview'); }}><b>{value.name}</b><small>{value.status} · {value.elapsed_seconds.toFixed(1)}s</small></button>{value.status === 'completed' && <input type="checkbox" aria-label={`Compare ${value.name}`} checked={comparison.includes(value.id)} disabled={!comparison.includes(value.id) && comparison.length >= 4} onChange={e => { setComparison(e.target.checked ? [...comparison, value.id] : comparison.filter(id => id !== value.id)); setTab('compare'); }}/>}</div>)}{!jobs.length && <p>Run a script from the Python editor to begin.</p>}</aside>
    <div className="research-content">{error && <p role="alert" className="python-error">{error}<button onClick={() => setError('')}>Dismiss</button></p>}
      {job && <><div className="research-heading"><b>{job.name}</b><span className={`job-status ${job.status}`}>{job.status}</span><span>{Math.round(job.progress*100)}% · {job.elapsed_seconds.toFixed(1)}s · peak {(job.peak_memory_bytes/1048576).toFixed(1)} MB</span><span className="toolbar-spacer"/>{!terminal.has(job.status) && <button disabled={cancelling} onClick={async () => { setCancelling(true); try { await api(`/research/${job.id}/cancel`, { method: 'POST' }); } catch (e) { setError(String(e)); setCancelling(false); } }}><Square size={12}/>{cancelling ? 'Stopping…' : 'Cancel run'}</button>}{result && <button onClick={() => void exportTable('json')}><Download size={13}/>Export result</button>}</div>
      {job.error && <pre className="runtime-error" role="alert">{job.error}</pre>}
      <nav className="research-tabs" aria-label="Research views">{['overview', 'orders', 'fills', 'trades', 'positions', 'contributions', 'equity', 'plots', 'logs', 'inputs', 'compare'].map(name => <button key={name} className={tab === name ? 'selected' : ''} onClick={async () => { setTab(name); if (name === 'inputs') { try { setSnapshot(await api(`/research/${job.id}/snapshot`)); } catch (e) { setError(String(e)); } } }}>{name}</button>)}</nav>
      {tab === 'overview' && result && <div className="research-overview"><div className="metric-grid">{Object.entries(result.metrics).map(([key, metric]) => <div key={key} title={metric.convention}><small>{key.replaceAll('_', ' ')}</small><strong>{metric.value == null ? 'Undefined' : metric.unit.startsWith('fraction') ? (metric.value*100).toFixed(2)+'%' : metric.value.toFixed(3)}</strong>{metric.undefined_reason && <small>{metric.undefined_reason}</small>}</div>)}</div><EquityChart result={result} theme={theme}/><div className="research-notes"><p>Final equity: <b>{money(result.final_portfolio.equity)} {result.settings.reporting_currency}</b> · Currency translation: {money(result.currency_translation)}</p>{result.final_portfolio.valuation_errors.map(value => <p key={value} className="runtime-error">{value}</p>)}<details><summary>Execution and metric conventions</summary>{result.limitations.map(value => <p key={value}>{value}</p>)}{Object.entries(result.metrics).map(([key, value]) => <p key={key}><b>{key.replaceAll('_', ' ')}:</b> {value.convention}</p>)}</details></div></div>}
      {tab in tables && <><div className="research-table-actions">{['orders', 'fills', 'trades', 'positions', 'contributions', 'equity'].includes(tab) && <button onClick={() => void exportTable(tab)}><Download size={12}/>Export {tab} CSV</button>}</div><ResultsTable key={`${job.id}-${tab}`} rows={tables[tab]}/></>}
      {tab === 'logs' && <div className="research-logs"><h4>Script output</h4><pre>{output.stdout || 'No standard output.'}</pre><h4>Context logs</h4><pre>{(result?.logs ?? output.logs)?.map(value => `${new Date(Number(value.time)*1000).toISOString()} ${value.message}`).join('\n') || 'No context logs yet. Running previews retain the latest 200 entries.'}</pre>{output.stderr && <><h4>Runtime diagnostics</h4><pre>{output.stderr}</pre></>}</div>}
      {tab === 'inputs' && <pre className="research-inputs">{snapshot ? JSON.stringify(snapshot, null, 2) : 'Loading saved input provenance…'}</pre>}
      {tab === 'compare' && <div className="research-comparison"><p>Select up to four completed runs in the left column. Comparisons retain each run’s currency, dates, and assumptions.</p><table><thead><tr><th>Metric</th>{comparison.map(id => <th key={id}>{jobs.find(value => value.id === id)?.name}</th>)}</tr></thead><tbody>{['currency', 'capital', 'fees / slippage', 'date range', 'snapshot', ...Object.keys(result?.metrics ?? compared[comparison[0]]?.metrics ?? {})].map(key => <tr key={key}><th>{key.replaceAll('_', ' ')}</th>{comparison.map(id => { const r = compared[id]; const j = jobs.find(value => value.id === id); return <td key={id}>{!r ? 'Loading…' : key === 'currency' ? r.settings.reporting_currency : key === 'capital' ? money(r.settings.initial_capital) : key === 'fees / slippage' ? `${r.settings.fee_bps} bps + ${r.settings.fee_per_order} / ${r.settings.slippage_bps} bps` : key === 'date range' ? `${new Date((r.equity[0]?.time ?? 0)*1000).toISOString().slice(0, 10)} → ${new Date(r.final_portfolio.time*1000).toISOString().slice(0, 10)}` : key === 'snapshot' ? j?.snapshot_hash.slice(0, 12) : r.metrics[key]?.value == null ? 'Undefined' : r.metrics[key].value!.toFixed(4)}</td>; })}</tr>)}</tbody></table></div>}
      {!result && tab === 'overview' && <p className="panel-empty">{terminal.has(job.status) ? 'This run did not produce a completed result. Saved inputs and runtime diagnostics remain available.' : 'The worker is calculating. Charts and saved datasets remain available while it runs.'}</p>}</>}
    </div></section>;
}
