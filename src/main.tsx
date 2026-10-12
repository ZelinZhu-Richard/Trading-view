import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { CandlestickChart, Check, ChevronDown, Columns2, Crosshair, Database,
  Download, Expand, Grid2X2, Link2, Moon, PanelBottom, PanelRight, Plus, Search,
  Square, Sun, Table2, Upload, X, ChartNoAxesCombined, PencilRuler, Layers, Magnet, Undo2, Redo2, Bell, Code2 } from 'lucide-react';
import type { AccountView, ChartState, Dataset, DatasetView, Drawing, IndicatorDefinition, Workspace } from './contracts';
import { Chart, type ChartHandle } from './Chart';
const ImportDialog = React.lazy(() => import('./ImportDialog').then(module => ({ default: module.ImportDialog })));
const ProviderDialog = React.lazy(() => import('./ProviderDialog').then(module => ({ default: module.ProviderDialog })));
import { api, download, formatPrice } from './api';
import { useWorkspace } from './useWorkspace';
import { useQuotes } from './useQuotes';
import { useCandles } from './useCandles';
import { intervalSource, linkedCharts, sharesGroup } from './data';
import { Watchlists } from './Watchlists';
const IndicatorDialog = React.lazy(() => import('./IndicatorDialog').then(module => ({ default: module.IndicatorDialog })));
const DrawingDialog = React.lazy(() => import('./DrawingDialog').then(module => ({ default: module.DrawingDialog })));
const AccountPanel = React.lazy(() => import('./AccountPanel').then(module => ({ default: module.AccountPanel })));
const ResearchPanel = React.lazy(() => import('./ResearchPanel').then(module => ({ default: module.ResearchPanel })));
const PythonPanel = React.lazy(() => import('./PythonPanel').then(module => ({ default: module.PythonPanel })));
const AlertDialog = React.lazy(() => import('./AlertDialog').then(module => ({ default: module.AlertDialog })));
import { useAlerts } from './useAlerts';
import { drawingTools, type DrawingKind } from './drawingGeometry';
import './styles.css';

function App() {
  const { workspace: ws, setWorkspace: setWs, saveStatus, saveError, reloadWorkspace, retrySave } = useWorkspace();
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [views, setViews] = useState<Record<string, DatasetView>>({});
  const [error, setError] = useState('');
  const [importOpen, setImportOpen] = useState(false);
  const [providerOpen, setProviderOpen] = useState(false);
  const [indicatorsOpen, setIndicatorsOpen] = useState(false);
  const [drawingMode, setDrawingMode] = useState<DrawingKind | null>(null);
  const [drawingMenu, setDrawingMenu] = useState(false);
  const [drawingSnap, setDrawingSnap] = useState(false);
  const [selectedDrawing, setSelectedDrawing] = useState<string | null>(null);
  const [objectsOpen, setObjectsOpen] = useState(false);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const alertData = useAlerts();
  const drawingHistory = useRef<Record<string, { past: Drawing[][]; future: Drawing[][] }>>({});
  const [definitions, setDefinitions] = useState<IndicatorDefinition[]>([]);
  const [search, setSearch] = useState('');
  const [panel, setPanel] = useState<'data' | 'details' | 'python' | 'research' | 'accounts'>('data');
  const [chartReady, setChartReady] = useState<Record<string, { cutoff: number | null; datasetId: string }>>({});
  const [accountView, setAccountView] = useState<AccountView | null>(null);
  const [researchId, setResearchId] = useState<string | null>(null);
  const [visibleWatchlistIds, setVisibleWatchlistIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);
  const [datasetPicker, setDatasetPicker] = useState(false);
  const handles = useRef<Record<string, ChartHandle | null>>({});
  const intervalController = useRef<AbortController | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const replay = accountView?.account.mode === 'replay' ? accountView : null;
  const cutoff = replay?.account.cursor ?? null;
  const candles = useCandles(replay ? [] : (ws?.charts.slice(0, ws.layout).filter(c => c.follow_live && c.dataset_id).map(c => c.dataset_id!) ?? []));
  const displayCharts = ws?.charts.map((chart, index) => replay ? { ...chart, dataset_id: replay.account.dataset_ids.includes(chart.dataset_id ?? '') ? chart.dataset_id : replay.account.dataset_ids[index % replay.account.dataset_ids.length] } : chart.follow_live && chart.dataset_id && candles.states[chart.dataset_id] ? { ...chart, dataset_id: candles.states[chart.dataset_id].dataset.id } : chart) ?? [];
  const displayViews = cutoff == null ? views : Object.fromEntries(Object.entries(views).map(([id, value]) => [id, { ...value, bars: value.bars.filter(bar => bar.complete && bar.end <= cutoff) }]));
  const active = displayCharts[ws?.active_chart ?? 0];
  const replayReady = !replay || displayCharts.slice(0, ws?.layout ?? 1).every(c => chartReady[c.id]?.cutoff === cutoff && chartReady[c.id]?.datasetId === c.dataset_id);
  const selected = datasets.find(d => d.id === active?.dataset_id);
  const view = active?.dataset_id ? displayViews[active.dataset_id] : undefined;
  const liveIds = new Set([selected?.instrument.id, ...visibleWatchlistIds]);
  const liveInstruments = datasets.filter((d, i, a) => liveIds.has(d.instrument.id) && a.findIndex(x => x.instrument.id === d.instrument.id) === i).map(d => d.instrument);
  const { quotes, connectionStatus } = useQuotes(replay ? [] : liveInstruments);
  const activeQuote = selected && !replay ? quotes[selected.instrument.id] : undefined;
  const baseChart = ws?.charts[ws.active_chart];
  const candleState = baseChart?.dataset_id ? candles.states[baseChart.dataset_id] : undefined;
  const canFollow = !!selected && ['coinbase', 'alpaca', 'alpha-vantage'].includes(selected.source) && selected.adjustment === 'raw' && !!selected.instrument.provider_symbols[selected.source];
  useEffect(() => {
    const values = Object.values(candles.states).map(value => value.dataset);
    if (values.length) setDatasets(previous => [...values, ...previous].filter((value, index, all) => all.findIndex(v => v.id === value.id) === index));
  }, [candles.states]);

  useEffect(() => { api<Dataset[]>('/datasets').then(setDatasets).catch(e => setError(String(e))); }, []);
  useEffect(() => { api<IndicatorDefinition[]>('/indicators').then(setDefinitions).catch(e => setError(String(e))); }, []);
  useEffect(() => { document.documentElement.dataset.theme = ws?.theme ?? 'dark'; }, [ws?.theme]);
  const edit = (fn: (value: Workspace) => Workspace) => setWs(value => value ? fn(value) : value);
  const editChart = (change: Partial<ChartState>) => edit(value => ({ ...value,
    charts: value.charts.map((c, i) => i === value.active_chart ? { ...c, ...change } : c),
  }));
  function changeDrawings(chartId: string, next: Drawing[]) {
    const current = ws?.charts.find(c => c.id === chartId); if (!current) return;
    const history = drawingHistory.current[chartId] ??= { past: [], future: [] };
    history.past = [...history.past, current.drawings].slice(-100); history.future = [];
    edit(value => ({ ...value, charts: value.charts.map(c => c.id === chartId ? { ...c, drawings: next } : c) }));
  }
  function drawingUndo(redo = false) {
    if (!active) return;
    const history = drawingHistory.current[active.id]; if (!history) return;
    const from = redo ? history.future : history.past, to = redo ? history.past : history.future;
    const next = from.pop(); if (!next) return;
    to.push(active.drawings); editChart({ drawings: next }); setSelectedDrawing(null);
  }
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (document.querySelector('dialog[open]') || event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLSelectElement) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'z') { event.preventDefault(); drawingUndo(event.shiftKey); }
      if ((event.key === 'Delete' || event.key === 'Backspace') && active && selectedDrawing) {
        event.preventDefault(); changeDrawings(active.id, active.drawings.filter(d => d.id !== selectedDrawing)); setSelectedDrawing(null);
      }
    };
    window.addEventListener('keydown', key); return () => window.removeEventListener('keydown', key);
  });
  async function selectDataset(data: Dataset) {
    if (replay) { setError('Exit replay to change the data universe.'); return; }
    if (!ws || !active) return;
    intervalController.current?.abort();
    const controller = new AbortController(); intervalController.current = controller;
    setBusy(true); setError(''); setDatasetPicker(false);
    try {
      const pool = [data, ...datasets];
      const changes = await Promise.all(linkedCharts(ws, active, 'symbol').map(async chart => {
        const previous = datasets.find(d => d.id === chart.dataset_id);
        const wanted = chart.id === active.id || (ws.link_interval && sharesGroup(chart, active)) ? data.interval : previous?.interval ?? data.interval;
        const source = intervalSource(data, pool, wanted);
        if (!source) throw new Error(`${data.instrument.symbol}: linked chart ${wanted} needs history at that interval. Connect or import it before linking these charts.`);
        const cached = source.interval === wanted ? source : pool.find(d => d.parent_id === source.id && d.interval === wanted);
        const next = cached ?? await api<Dataset>(`/datasets/${source.id}/aggregate?interval=${wanted}`, { method: 'POST', signal: controller.signal });
        return { chartId: chart.id, oldId: chart.dataset_id, data: next };
      }));
      if (controller.signal.aborted) return;
      setDatasets(previous => [...changes.map(c => c.data), ...previous].filter((d, i, all) => all.findIndex(x => x.id === d.id) === i));
      edit(value => ({ ...value, charts: value.charts.map(chart => {
        const change = changes.find(c => c.chartId === chart.id && c.oldId === chart.dataset_id);
        return change ? { ...chart, dataset_id: change.data.id, follow_live: chart.follow_live && ['coinbase', 'alpaca', 'alpha-vantage'].includes(change.data.source) } : chart;
      }) }));
    } catch (e) { if (!controller.signal.aborted) setError(String(e)); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  function imported(data: Dataset) {
    setDatasets(previous => [data, ...previous.filter(d => d.id !== data.id)]);
    selectDataset(data); setImportOpen(false);
    edit(value => ({ ...value, watchlists: value.watchlists.map(w => w.id === value.active_watchlist && !w.items.some(item => item.instrument_id === data.instrument.id)
      ? { ...w, items: [...w.items, { schema_version: 1, instrument_id: data.instrument.id, section: '' }] } : w) }));
  }
  async function example() {
    setBusy(true); setError('');
    try { imported(await api<Dataset>('/examples/dataset', { method: 'POST' })); }
    catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  function layout(value: 1 | 2 | 4) {
    edit(previous => ({ ...previous, layout: value, active_chart: Math.min(previous.active_chart, value - 1),
      charts: previous.charts.map(c => ({ ...c, dataset_id: c.dataset_id ?? active?.dataset_id ?? null })) }));
  }
  async function interval(value: string) {
    if (!selected || !ws || !active) return;
    intervalController.current?.abort();
    const controller = new AbortController(); intervalController.current = controller;
    setBusy(true); setError('');
    try {
      const targets = linkedCharts(ws, active, 'interval');
      const changes = await Promise.all(targets.map(async chart => {
        const current = datasets.find(d => d.id === displayCharts.find(c => c.id === chart.id)?.dataset_id);
        const source = intervalSource(current, datasets, value);
        if (!source) throw new Error(`${current?.instrument.symbol ?? chart.id}: ${value} is unavailable in this dataset and its recorded source.`);
        const cached = source.interval === value ? source : datasets.find(d => d.parent_id === source.id && d.interval === value);
        const data = cached ?? await api<Dataset>(`/datasets/${source.id}/aggregate?interval=${value}`, { method: 'POST', signal: controller.signal });
        return { chartId: chart.id, oldId: chart.dataset_id, data };
      }));
      if (controller.signal.aborted) return;
      setDatasets(previous => [...changes.map(c => c.data), ...previous].filter((d, i, all) => all.findIndex(x => x.id === d.id) === i));
      edit(previous => ({ ...previous, charts: previous.charts.map(chart => {
        const change = changes.find(c => c.chartId === chart.id && c.oldId === chart.dataset_id);
        return change ? { ...chart, dataset_id: change.data.id } : chart;
      }) }));
    } catch (e) { if (!controller.signal.aborted) setError(String(e)); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  const visibleDatasets = datasets.filter(d => `${d.instrument.symbol} ${d.instrument.name} ${d.instrument.exchange}`.toLowerCase().includes(search.toLowerCase()));

  if (!ws) return <div className="loading-page"><div className="brand-mark">M</div><h1>Market Workbench</h1><p>{saveError || saveStatus}</p><button onClick={() => void reloadWorkspace()}>Reconnect</button></div>;

  return <div className="app-shell" style={{ '--sidebar-width': `${ws.sidebar_width}px`, '--bottom-height': `${ws.bottom_height}px` } as React.CSSProperties}>
    <header className="app-header"><div className="brand"><span className="brand-mark">M</span><span>Market <b>Workbench</b></span><span className="local-pill">LOCAL</span></div><span className="workspace-title">{ws.name}<ChevronDown size={13}/></span><div className="header-actions"><span className={`save-state ${saveError ? 'unsaved' : ''}`}><Check size={13}/>{saveStatus}</span><button className="icon-button" aria-label="Export workspace" onClick={() => download('market-workbench-workspace.json', JSON.stringify(ws, null, 2))}><Download size={17}/></button><button className="icon-button" aria-label="Import workspace" onClick={() => fileInput.current?.click()}><Upload size={17}/></button><input ref={fileInput} hidden type="file" accept=".json" onChange={async e => {
      const file = e.target.files?.[0]; if (!file) return;
      try {
        const draft = JSON.parse(await file.text());
        const current = await api<Workspace>('/workspaces/default');
        await api<Workspace>('/workspaces/default', { method: 'PUT', body: JSON.stringify({ ...draft, id: 'default', revision: current.revision }) });
        await reloadWorkspace();
      } catch (err) { setError(String(err)); }
      e.target.value = '';
    }}/><button className="icon-button" aria-label={ws.theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'} onClick={() => edit(v => ({ ...v, theme: v.theme === 'dark' ? 'light' : 'dark' }))}>{ws.theme === 'dark' ? <Sun size={17}/> : <Moon size={17}/>}</button></div></header>
    <div className="workspace-toolbar"><div className="relative"><button disabled={!!replay} className="symbol-picker" onClick={() => setDatasetPicker(!datasetPicker)}><Search size={16}/><b>{selected?.instrument.symbol ?? 'Find instrument'}</b><ChevronDown size={13}/></button>{datasetPicker && <div className="popover dataset-picker"><input aria-label="Search datasets" value={search} onChange={e => setSearch(e.target.value)} placeholder="Symbol, name, or venue" autoFocus/>{visibleDatasets.map(d => <button key={d.id} data-dataset-id={d.id} title={`${d.row_count.toLocaleString()} bars · saved ${new Date(d.created_at).toLocaleString()}`} onClick={() => selectDataset(d)}><span><b>{d.instrument.symbol}</b><small>{d.instrument.exchange} · {d.instrument.quote_currency}</small></span><span>{d.interval} <small>{d.source}</small></span></button>)}{!visibleDatasets.length && <p>No matching datasets. Import one to begin.</p>}</div>}</div>
      <span className="divider"/><label className="sr-only" htmlFor="interval">Chart interval</label><select id="interval" className="compact-select" value={selected?.interval ?? '1d'} disabled={!selected || busy || !!replay} onChange={e => void interval(e.target.value)}>{['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1mo'].map(i => <option key={i} value={i} disabled={!intervalSource(selected, datasets, i)}>{i.toUpperCase()}</option>)}</select>
      <span className="divider"/><CandlestickChart size={17}/><select className="compact-select chart-kind" aria-label="Chart type" value={active?.kind} onChange={e => editChart({ kind: e.target.value as ChartState['kind'] })}>{['candlestick', 'bar', 'line', 'area', 'baseline', 'heikin-ashi'].map(k => <option key={k} value={k}>{k.replace('-', ' ')}</option>)}</select><select className="compact-select scale-select" aria-label="Price scale" value={active?.scale} onChange={e => editChart({ scale: e.target.value as ChartState['scale'] })}><option value="linear">Linear</option><option value="logarithmic">Log</option><option value="percentage">Percent</option></select>
      <button className="indicator-button" disabled={!selected} onClick={() => setIndicatorsOpen(true)}><ChartNoAxesCombined size={15}/>Indicators</button><span className="toolbar-spacer"/><div className="layout-buttons">{([1, 2, 4] as const).map((n, i) => { const Icon = [Square, Columns2, Grid2X2][i]; return <button key={n} className={`icon-button ${ws.layout === n ? 'selected' : ''}`} aria-label={`${n} chart layout`} aria-pressed={ws.layout === n} onClick={() => layout(n)}><Icon size={17}/></button>; })}</div>
      <div className="relative"><button className="icon-button" aria-label="Chart linking settings" onClick={() => setLinkOpen(!linkOpen)}><Link2 size={17}/></button>{linkOpen && <div className="popover link-popover"><strong>Link chart group</strong><label>Active chart group<select aria-label="Active chart link group" value={active?.link_group ?? ''} onChange={e => editChart({ link_group: e.target.value || null })}><option value="main">Main</option><option value="second">Second</option><option value="third">Third</option><option value="">Independent</option></select></label>{(['symbol', 'interval', 'crosshair', 'range'] as const).map(key => <label key={key}><input type="checkbox" checked={ws[`link_${key}`]} onChange={e => edit(v => ({ ...v, [`link_${key}`]: e.target.checked }))}/>{key === 'range' ? 'Visible time range' : key}</label>)}</div>}</div>
      <button className="icon-button" aria-label="Local alerts" onClick={() => setAlertsOpen(true)}><Bell size={17}/></button><span className="divider"/><button className="icon-button" aria-label="Connect data source" onClick={() => setProviderOpen(true)}><Database size={17}/></button><button className="import-button" onClick={() => setImportOpen(true)}><Plus size={16}/>Import data</button>
    </div>
    {(error || saveError) && <div className="error-banner" role="alert"><span>{error || saveError}</span>{saveError && <><button onClick={retrySave}>Retry save</button><button onClick={() => void reloadWorkspace()}>Reload saved version</button></>}<button className="icon-button" aria-label="Dismiss message" onClick={() => setError('')}><X size={15}/></button></div>}
    {replay && <div className="replay-banner"><b>HISTORICAL REPLAY</b><span>{replay.account.name} · {new Date(cutoff!*1000).toISOString().replace('T', ' ').slice(0, 19)} UTC</span><span>Future bars hidden across charts</span><button onClick={() => { setPanel('accounts'); edit(v => ({ ...v, bottom_open: true })); }}>Replay controls</button><button onClick={() => setAccountView(null)}>Exit replay</button></div>}
    <main className={`workspace-body ${ws.sidebar_open ? '' : 'sidebar-closed'}`}>
      <aside className="tools-rail" aria-label="Chart tools"><button className={`icon-button ${!drawingMode ? 'selected' : ''}`} aria-label="Crosshair cursor" onClick={() => setDrawingMode(null)}><Crosshair size={20}/></button>
        <div className="relative"><button className={`icon-button ${drawingMode ? 'selected' : ''}`} aria-label="Drawing tools" aria-expanded={drawingMenu} onClick={() => setDrawingMenu(!drawingMenu)}><PencilRuler size={19}/></button>{drawingMenu && <div className="popover drawing-tool-menu">{drawingTools.map(tool => <button key={tool.kind} onClick={() => { setDrawingMode(tool.kind); setDrawingMenu(false); }}>{tool.name}</button>)}</div>}</div>
        <button className="icon-button" aria-label="Drawing objects" onClick={() => setObjectsOpen(true)}><Layers size={18}/></button>
        <button className={`icon-button ${drawingSnap ? 'selected' : ''}`} aria-label="Snap drawing anchors to OHLC" aria-pressed={drawingSnap} onClick={() => setDrawingSnap(!drawingSnap)}><Magnet size={18}/></button>
        <button className="icon-button" aria-label="Undo drawing action" disabled={!active || !drawingHistory.current[active.id]?.past.length} onClick={() => drawingUndo()}><Undo2 size={18}/></button>
        <button className="icon-button" aria-label="Redo drawing action" disabled={!active || !drawingHistory.current[active.id]?.future.length} onClick={() => drawingUndo(true)}><Redo2 size={18}/></button><span className="rail-divider"/><button className="icon-button" aria-label="Fit chart to data" onClick={() => active && handles.current[active.id]?.fit()}><Expand size={19}/></button><button className="icon-button" aria-label="Export chart image" disabled={!view} onClick={() => { if (!active) return; const url = handles.current[active.id]?.image(); if (url) { const a = document.createElement('a'); a.href = url; a.download = `chart-${selected?.instrument.symbol}.png`; a.click(); } }}><Download size={19}/></button><button className="icon-button" aria-label="Toggle data panel" aria-pressed={ws.bottom_open} onClick={() => edit(v => ({ ...v, bottom_open: !v.bottom_open }))}><Table2 size={19}/></button><span className="toolbar-spacer"/><button className="icon-button" aria-label="Toggle watchlist" onClick={() => edit(v => ({ ...v, sidebar_open: !v.sidebar_open }))}><PanelRight size={19}/></button></aside>
      <section className="center-workspace"><div className={`chart-grid layout-${ws.layout}`}>{displayCharts.slice(0, ws.layout).map((chart, i) => <Chart rangeIdentity={chart.follow_live && cutoff == null ? ws.charts[i].dataset_id ?? undefined : undefined} cutoff={cutoff} onReady={(readyCutoff, datasetId) => setChartReady(previous => previous[chart.id]?.cutoff === readyCutoff && previous[chart.id]?.datasetId === datasetId ? previous : { ...previous, [chart.id]: { cutoff: readyCutoff, datasetId } })} key={chart.id} chart={chart} definitions={definitions} drawingMode={drawingMode} drawingSnap={drawingSnap} selectedDrawing={selectedDrawing} onDrawingSelect={setSelectedDrawing} onDrawingsChange={values => changeDrawings(chart.id, values)} onDrawingFinish={() => setDrawingMode(null)} theme={ws.theme} active={i === ws.active_chart} onActivate={() => edit(v => ({ ...v, active_chart: i }))} register={handle => { handles.current[chart.id] = handle; }} onLoaded={value => setViews(previous => Object.fromEntries([[value.dataset.id, value], ...Object.entries(previous).filter(([id]) => id !== value.dataset.id)].slice(0, 16)))}
        onRange={range => { if (ws.link_range && i === ws.active_chart) ws.charts.slice(0, ws.layout).filter(c => c.id !== chart.id && sharesGroup(c, chart)).forEach(c => handles.current[c.id]?.range(range)); }}
        onCrosshair={time => { if (ws.link_crosshair && i === ws.active_chart) ws.charts.slice(0, ws.layout).filter(c => c.id !== chart.id && sharesGroup(c, chart)).forEach(c => handles.current[c.id]?.crosshair(time)); }}/>)}</div>
        {!datasets.length && <div className="start-actions"><button className="primary" onClick={() => setImportOpen(true)}><Upload size={16}/>Import CSV</button><button disabled={busy} onClick={() => void example()}>Open synthetic example <span>↗</span></button></div>}
        <div className="chart-footer">{drawingMode && <span className="drawing-instruction">{drawingTools.find(t => t.kind === drawingMode)?.instruction} <button onClick={() => setDrawingMode(null)}>Cancel</button></span>}<span>{selected ? `${selected.instrument.quote_currency} · ${selected.instrument.timezone} · ${selected.adjustment}` : 'No dataset selected'}</span><span className="toolbar-spacer"/>{!replay && <><label><input aria-label="Follow provider candles" type="checkbox" disabled={!canFollow} checked={baseChart?.follow_live ?? false} onChange={e => editChart({ follow_live: e.target.checked, ...(!e.target.checked && selected ? { dataset_id: selected.id } : {}) })}/>Follow candles</label>{baseChart?.follow_live && <span className="candle-status" role="status" title={`${candleState?.message ?? 'Connecting to completed-candle updates.'} ${candleState?.last_success ? 'Last checked '+new Date(candleState.last_success).toLocaleString() : ''}`}>
          {candles.error || (candles.connection !== 'connected' ? `Cached · ${candles.connection}` : candleState?.status === 'stale' ? 'Cached · stale' : candleState?.status === 'current' ? 'Completed candles · checked' : candleState?.status ?? 'Connecting')}
          {(candles.connection === 'disconnected' || candleState?.status === 'stale') && <button onClick={async () => { candles.reconnect(); if (baseChart?.dataset_id) try { await api(`/candles/${baseChart.dataset_id}/retry`, { method: 'POST' }); } catch (e) { setError(String(e)); } }}>Retry</button>}
        </span>}</>}<label><input type="checkbox" checked={active?.show_volume ?? true} onChange={e => editChart({ show_volume: e.target.checked })}/>Volume</label><select aria-label="Chart timezone" value={active?.timezone} onChange={e => editChart({ timezone: e.target.value })}>{['UTC', 'America/New_York', 'Asia/Shanghai', 'Europe/London'].map(v => <option key={v}>{v}</option>)}</select></div>
        {ws.bottom_open && <><div className="resize-handle horizontal" role="separator" aria-label="Resize data panel" aria-orientation="horizontal" tabIndex={0} onKeyDown={e => { if (e.key === 'ArrowUp' || e.key === 'ArrowDown') edit(v => ({ ...v, bottom_height: Math.max(100, Math.min(600, v.bottom_height + (e.key === 'ArrowUp' ? 20 : -20))) })); }} onPointerDown={e => { const start = e.clientY, initial = ws.bottom_height; e.currentTarget.setPointerCapture(e.pointerId); const move = (event: PointerEvent) => edit(v => ({ ...v, bottom_height: Math.max(100, Math.min(600, initial + start - event.clientY)) })); const end = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', end); }; window.addEventListener('pointermove', move); window.addEventListener('pointerup', end); }}/>
          <section className="bottom-panel"><div className="panel-tabs"><button className={panel === 'data' ? 'selected' : ''} onClick={() => setPanel('data')}><Table2 size={14}/>Data table</button><button className={panel === 'details' ? 'selected' : ''} onClick={() => setPanel('details')}><Database size={14}/>Dataset details</button><button className={panel === 'python' ? 'selected' : ''} onClick={() => { setPanel('python'); edit(v => ({ ...v, bottom_height: Math.max(400, v.bottom_height) })); }}><Code2 size={14}/>Python editor</button><button className={panel === 'research' ? 'selected' : ''} onClick={() => { setPanel('research'); edit(v => ({ ...v, bottom_height: Math.max(450, v.bottom_height) })); }}>Research results</button><button className={panel === 'accounts' ? 'selected' : ''} onClick={() => { setPanel('accounts'); edit(v => ({ ...v, bottom_height: Math.max(420, v.bottom_height) })); }}>Replay & paper</button><span className="toolbar-spacer"/><span>{view?.bars.length.toLocaleString() ?? 0} bars</span><button className="icon-button" aria-label="Collapse data panel" onClick={() => edit(v => ({ ...v, bottom_open: false }))}><PanelBottom size={15}/></button></div>
            {panel === 'accounts' ? <React.Suspense fallback={<p className="panel-empty">Opening accounts…</p>}><AccountPanel datasets={datasets} activeDataset={active?.dataset_id ?? undefined} view={accountView} onView={setAccountView} chartsReady={replayReady}/></React.Suspense> : panel === 'research' ? <React.Suspense fallback={<p className="panel-empty">Opening research results…</p>}><ResearchPanel selectedId={researchId} onSelect={setResearchId} theme={ws.theme}/></React.Suspense> : panel === 'python' ? <React.Suspense fallback={<p className="panel-empty">Opening local Python editor…</p>}><PythonPanel theme={ws.theme} replay={replay} datasets={datasets} activeDataset={active?.dataset_id ?? undefined} onRun={job => { setResearchId(job.id); setPanel('research'); }}/></React.Suspense> : panel === 'data' ? <div className="table-wrap"><table><caption className="sr-only">Source OHLC values, most recent 200 bars, in UTC</caption><thead><tr><th>Date · UTC</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Volume</th><th>Bar status</th></tr></thead><tbody>{view?.bars.slice(-200).reverse().map(b => <tr key={b.start}><td>{new Date(b.start * 1000).toISOString().slice(0, 16).replace('T', ' ')}</td>{[b.open, b.high, b.low, b.close].map((v, i) => <td key={i}>{formatPrice(v)}</td>)}<td>{b.volume?.toLocaleString() ?? 'Missing'}</td><td>{b.complete ? 'Complete' : 'Incomplete'}</td></tr>)}</tbody></table>{!view && <p className="panel-empty">Imported chart values will appear here.</p>}</div> : <div className="dataset-details">{selected ? <><dl><dt>Provider / feed</dt><dd>{selected.source} / {selected.feed}</dd><dt>Available history</dt><dd>{new Date(selected.first_start * 1000).toLocaleDateString()} – {new Date(selected.last_end * 1000).toLocaleDateString()}</dd><dt>Saved locally</dt><dd>{new Date(selected.created_at).toLocaleString()}</dd><dt>Dataset hash</dt><dd className="hash">{selected.hash}</dd></dl>{selected.limitations.map(l => <p className="notice" key={l}>{l}</p>)}</> : <p className="panel-empty">Select a dataset to inspect its source and coverage.</p>}</div>}
          </section></>}
      </section>
      {ws.sidebar_open && <><div className="resize-handle vertical" role="separator" aria-label="Resize watchlist" aria-orientation="vertical" tabIndex={0} onKeyDown={e => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') edit(v => ({ ...v, sidebar_width: Math.max(220, Math.min(500, v.sidebar_width + (e.key === 'ArrowLeft' ? 20 : -20))) })); }} onPointerDown={e => { const start = e.clientX, initial = ws.sidebar_width; e.currentTarget.setPointerCapture(e.pointerId); const move = (event: PointerEvent) => edit(v => ({ ...v, sidebar_width: Math.max(220, Math.min(500, initial + start - event.clientX)) })); const end = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', end); }; window.addEventListener('pointermove', move); window.addEventListener('pointerup', end); }}/>
      <aside className="watchlist-panel"><Watchlists workspace={ws} datasets={datasets} views={displayViews} quotes={replay ? {} : quotes} selectedInstrument={selected?.instrument.id} onSelect={selectDataset} onVisible={setVisibleWatchlistIds} onChange={(watchlists, active_watchlist) => edit(v => ({ ...v, watchlists, active_watchlist }))}/>
        <section className="instrument-details"><span className="eyebrow">INSTRUMENT DETAILS</span><h2>{selected?.instrument.symbol ?? 'Your market, in focus.'}</h2><p>{selected?.instrument.name ?? 'Select an instrument to explore its price history and data coverage.'}</p>{selected && <><div className="headline-price">{formatPrice(activeQuote?.price ?? view?.bars.at(-1)?.close)}<span>{selected.instrument.quote_currency}</span></div><span className="data-status"><i/>{activeQuote ? `${activeQuote.freshness} quote · ${new Date(activeQuote.timestamp * 1000).toLocaleTimeString()}` : replay ? 'Replay · completed bars only' : selected.source === 'fixture' ? 'Synthetic example' : 'Historical dataset'}</span><dl><dt>Source</dt><dd>{selected.source}</dd><dt>Interval</dt><dd>{selected.interval}</dd><dt>Bars</dt><dd>{selected.row_count.toLocaleString()}</dd><dt>Calendar</dt><dd>{selected.instrument.calendar}</dd></dl><p className="small-note">{selected.source === 'fixture' ? 'Generated for research examples. These are not market prices.' : 'Follow candles checks for completed provider bars. With it off, the saved chart stays fixed. Streaming quotes update this summary separately.'}</p></>}</section>
      </aside></>}
    </main><footer className="status-bar"><span><i className={`connection-dot ${connectionStatus === 'connected' ? '' : 'offline'}`}/>{connectionStatus === 'connected' ? 'Local service connected' : 'Local service disconnected'}</span><span>Data stays on this computer</span><span className="toolbar-spacer"/><a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">Charts by TradingView</a><span>Market Workbench 0.1</span></footer>
    {alertData.notice && <div className="alert-toast" role="status"><Bell size={16}/><button onClick={() => { setAlertsOpen(true); alertData.dismiss(); }}><b>{alertData.notice.alert_name}</b><span>{alertData.notice.condition.replaceAll('_', ' ')} {alertData.notice.threshold} · value {formatPrice(alertData.notice.value)}</span></button><button className="icon-button" aria-label="Dismiss alert notification" onClick={alertData.dismiss}><X size={14}/></button></div>}
    <React.Suspense fallback={<div className="controls-loading" role="status">Opening controls…</div>}>
    {alertsOpen && active && <AlertDialog alerts={alertData.alerts} events={alertData.events} status={alertData.status} serviceError={alertData.error} datasets={datasets} chart={active} definitions={definitions} onRefresh={alertData.refresh} onClose={() => setAlertsOpen(false)}/>}
    {objectsOpen && active && <DrawingDialog drawings={active.drawings} instrumentId={selected?.instrument.id} bars={view?.bars} selected={selectedDrawing} onSelect={setSelectedDrawing} onChange={values => changeDrawings(active.id, values)} onClose={() => setObjectsOpen(false)}/>}
    {indicatorsOpen && active && <IndicatorDialog chart={active} view={view} definitions={definitions} templates={ws.indicator_templates} onChange={indicators => editChart({ indicators })} onTemplates={indicator_templates => edit(v => ({ ...v, indicator_templates }))} onClose={() => setIndicatorsOpen(false)}/>}
    {providerOpen && <ProviderDialog onClose={() => setProviderOpen(false)} onLoaded={value => { imported(value); setProviderOpen(false); }}/>}
    {importOpen && <ImportDialog onClose={() => setImportOpen(false)} onImported={imported}/>}
    </React.Suspense>
  </div>;
}

createRoot(document.getElementById('root')!).render(<App/>);
