import { useModal } from './useModal';
import { CandleUpdates } from './CandleUpdates';
import { useState } from 'react';
import { Pause, Play, Plus, Trash2, X } from 'lucide-react';
import type { AlertDefinition, AlertEvent, AlertServiceStatus, ChartState, Dataset, IndicatorDefinition } from './contracts';
import { api, formatPrice } from './api';

interface Props {
  alerts: AlertDefinition[]; events: AlertEvent[]; status: AlertServiceStatus | null; serviceError: string;
  datasets: Dataset[]; chart: ChartState; definitions: IndicatorDefinition[];
  onRefresh: () => Promise<void>; onClose: () => void;
}
export function AlertDialog({ alerts, events, status, serviceError, datasets, chart, definitions, onRefresh, onClose }: Props) {
  const dialog = useModal();
  const [draft, setDraft] = useState<AlertDefinition | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<'rules' | 'history'>('rules');
  async function save(value: AlertDefinition) {
    setBusy(true); setError('');
    try {
      const saved = await api<AlertDefinition>(`/alerts/${value.id}`, { method: 'PUT', body: JSON.stringify(value) });
      if (draft?.id === value.id) setDraft(saved);
      await onRefresh();
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  const indicator = definitions.find(d => d.id === draft?.indicator?.definition_id);
  return <dialog className="modal alert-dialog" ref={dialog} onCancel={onClose} aria-labelledby="alerts-title">
    <header><div><span className="eyebrow">COMPLETED BAR CONDITIONS</span><h2 id="alerts-title">Local alerts</h2></div><button className="icon-button" aria-label="Close alerts" onClick={onClose}><X size={18}/></button></header>
    <div className="alert-service-status"><b>{!status ? 'Service disconnected' : !status.running ? 'Evaluation stopped' : status.error ? 'Evaluation needs attention' : 'Evaluation running'}</b><span>{status?.error || serviceError || status?.scope}</span></div>
    <CandleUpdates/><div className="panel-tabs"><button className={tab === 'rules' ? 'selected' : ''} onClick={() => setTab('rules')}>Alert rules · {alerts.length}</button><button className={tab === 'history' ? 'selected' : ''} onClick={() => setTab('history')}>Trigger history · {events.length}</button><span className="toolbar-spacer"/><button disabled={!chart.dataset_id || busy} onClick={() => { setTab('rules'); setError(''); setDraft({ schema_version: 1, id: crypto.randomUUID(), revision: 0, name: 'Price alert', dataset_id: chart.dataset_id!, field: 'close', indicator: null, output_id: 'value', condition: 'crosses_above', threshold: 0, recurring: false, enabled: true, completed_bars: true }); }}><Plus size={14}/>New alert</button></div>
    <div className="alert-content">{tab === 'history' ? <div className="table-wrap"><table><caption>Last 200 triggers · UTC · history remains after deleting a rule</caption><thead><tr><th>Completed bar</th><th>Alert</th><th>Condition</th><th>Value</th><th>Threshold</th><th>Source / feed</th></tr></thead><tbody>{events.map(e => <tr key={e.id}><td>{new Date(e.bar_end*1000).toISOString().replace('T', ' ').slice(0, 19)}</td><td>{e.alert_name}</td><td>{e.condition.replaceAll('_', ' ')}</td><td>{formatPrice(e.value)}</td><td>{formatPrice(e.threshold)}</td><td>{e.source} / {e.feed}</td></tr>)}</tbody></table>{!events.length && <p className="panel-empty">No conditions have triggered yet.</p>}</div> : <div className="alert-rules-layout"><section className="alert-rules">{alerts.map(alert => {
      const state = status?.states[alert.id], dataset = datasets.find(d => d.id === alert.dataset_id);
      return <article key={alert.id}><button className="alert-rule-name" disabled={busy} onClick={() => { setDraft(structuredClone(alert)); setError(''); }}><b>{alert.name}</b><span>{dataset?.instrument.symbol ?? 'Unknown dataset'} · {alert.condition.replaceAll('_', ' ')} {alert.threshold}</span></button><div><button className="icon-button" disabled={busy} aria-label={`${alert.enabled ? 'Pause' : 'Resume'} alert ${alert.name}`} onClick={() => void save({ ...alert, enabled: !alert.enabled })}>{alert.enabled ? <Pause size={13}/> : <Play size={13}/>}</button><button className="icon-button" disabled={busy} aria-label={`Delete alert ${alert.name}`} onClick={async () => { setBusy(true); try { await api(`/alerts/${alert.id}`, { method: 'DELETE' }); if (draft?.id === alert.id) setDraft(null); await onRefresh(); } catch (e) { setError(String(e)); } finally { setBusy(false); } }}><Trash2 size={13}/></button></div><p>{!alert.enabled ? 'Paused' : state?.message ?? 'Waiting for baseline'}{state && <><br/>Last completed data: {new Date(state.last_end*1000).toLocaleString()}</>}</p></article>;
    })}{!alerts.length && <p className="small-note">Create a rule from the active chart. A new rule starts after the latest locally available completed bar.</p>}</section>
      <section className="alert-edit">{draft ? <form onSubmit={e => { e.preventDefault(); void save(draft); }}><h3>{draft.revision ? 'Edit alert' : 'New alert'}</h3><div className="indicator-fields"><label>Name<input required maxLength={100} value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })}/></label><label>Dataset<select value={draft.dataset_id} onChange={e => setDraft({ ...draft, dataset_id: e.target.value })}>{datasets.map(d => <option key={d.id} value={d.id}>{d.instrument.symbol} · {d.interval} · {d.feed} · {d.created_at.slice(0, 10)}</option>)}</select></label>
      <label>Value source<select value={draft.indicator?.id ?? `price:${draft.field}`} onChange={e => {
        if (e.target.value.startsWith('price:')) setDraft({ ...draft, indicator: null, field: e.target.value.slice(6) as AlertDefinition['field'] });
        else { const selected = chart.indicators.find(i => i.id === e.target.value)!; const d = definitions.find(d => d.id === selected.definition_id); setDraft({ ...draft, indicator: selected, output_id: d?.outputs[0].id ?? 'value' }); }
      }}>{['open', 'high', 'low', 'close'].map(field => <option key={field} value={`price:${field}`}>Price · {field}</option>)}{chart.indicators.map(i => <option key={i.id} value={i.id}>{definitions.find(d => d.id === i.definition_id)?.name ?? i.definition_id}</option>)}{draft.indicator && !chart.indicators.some(i => i.id === draft.indicator?.id) && <option value={draft.indicator.id}>{indicator?.name ?? draft.indicator.definition_id} · saved parameters</option>}</select></label>
      {draft.indicator && <label>Indicator output<select value={draft.output_id} onChange={e => setDraft({ ...draft, output_id: e.target.value })}>{indicator?.outputs.map(o => <option value={o.id} key={o.id}>{o.id}</option>)}</select></label>}
      <label>Condition<select value={draft.condition} onChange={e => setDraft({ ...draft, condition: e.target.value as AlertDefinition['condition'] })}>{['above', 'below', 'crosses_above', 'crosses_below'].map(v => <option key={v} value={v}>{v.replaceAll('_', ' ')}</option>)}</select></label><label>Threshold<input required type="number" step="any" value={draft.threshold} onChange={e => setDraft({ ...draft, threshold: Number(e.target.value) })}/></label></div>
      <label className="alert-checkbox"><input type="checkbox" checked={draft.recurring} onChange={e => setDraft({ ...draft, recurring: e.target.checked })}/>Repeat on matching completed bars</label><label className="alert-checkbox"><input type="checkbox" checked={draft.completed_bars} disabled/>Evaluate completed bars only</label><p className="small-note">Editing conditions or resuming a paused rule starts a fresh baseline at the latest local completed bar. Earlier triggers remain in history. Indicator parameters are captured when selected.</p>
      <button className="primary" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save alert'}</button></form> : <p className="small-note">Select a rule to edit it, or create a new alert. Once-only rules stop after their first trigger. Recurring threshold rules can trigger on every qualifying bar.</p>}{error && <p className="error" role="alert">{error}</p>}</section>
    </div>}</div>
  </dialog>;
}
