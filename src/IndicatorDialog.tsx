import { useModal } from './useModal';
import { useEffect, useRef, useState } from 'react';
import { Eye, EyeOff, Plus, Search, Settings2, Trash2, X } from 'lucide-react';
import type { ChartState, DatasetView, IndicatorDefinition, IndicatorInstance, IndicatorResponse } from './contracts';
import { api } from './api';

interface Props {
  chart: ChartState;
  view?: DatasetView;
  definitions: IndicatorDefinition[];
  templates: Record<string, IndicatorInstance[]>;
  onChange: (values: IndicatorInstance[]) => void;
  onTemplates: (values: Record<string, IndicatorInstance[]>) => void;
  onClose: () => void;
}
const label = (text: string) => text.replaceAll('_', ' ');

export function IndicatorDialog({ chart, view, definitions, templates, onChange, onTemplates, onClose }: Props) {
  const dialog = useModal();
  const request = useRef<AbortController | null>(null);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<IndicatorDefinition | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [params, setParams] = useState<IndicatorInstance['parameters']>({});
  const [color, setColor] = useState('#70b8f0');
  const [width, setWidth] = useState(2);
  const [pane, setPane] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [templateName, setTemplateName] = useState('');
  const hasVolume = view?.bars.some(b => b.volume != null) ?? false;
  useEffect(() => () => request.current?.abort(), []);

  function choose(definition: IndicatorDefinition, instance?: IndicatorInstance) {
    setSelected(definition); setEditing(instance?.id ?? null); setError('');
    const defaults = Object.fromEntries(Object.entries(definition.parameters).filter(([, v]) => v.default != null).map(([k, v]) => [k, v.default!])) as IndicatorInstance['parameters'];
    if (definition.id === 'historical_volatility' && view?.dataset.instrument.calendar === '24/7' && view.dataset.interval === '1d') defaults.bars_per_year = 365;
    setParams({ ...defaults, ...instance?.parameters });
    setColor(instance?.color ?? '#70b8f0'); setWidth(instance?.width ?? 2);
    setPane(instance?.pane ?? (definition.outputs[0].pane === 'price' ? 0 : definition.outputs[0].pane === 'volume' ? 1 : Math.max(1, ...chart.indicators.map(i => i.pane)) + 1));
  }

  async function apply() {
    if (!selected || !chart.dataset_id) return;
    if (!editing && chart.indicators.length >= 50) { setError('A chart supports up to 50 indicator instances.'); return; }
    setBusy(true); setError('');
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    const instance: IndicatorInstance = { schema_version: 1, id: editing ?? crypto.randomUUID(), definition_id: selected.id,
      parameters: params, color, width, pane, visible: true };
    try {
      const check = await api<IndicatorResponse>('/indicators/calculate', { method: 'POST', signal: controller.signal, body: JSON.stringify({ dataset_id: chart.dataset_id, instances: [instance] }) });
      if (controller.signal.aborted) return;
      const result = check.results[0];
      if (result.status !== 'ready') throw new Error(result.message);
      onChange(editing ? chart.indicators.map(i => i.id === editing ? instance : i) : [...chart.indicators, instance]);
      setEditing(instance.id);
    } catch (e) { if (!controller.signal.aborted) setError(String(e)); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }

  return <dialog className="modal indicator-dialog" ref={dialog} onCancel={onClose} aria-labelledby="indicators-title">
    <header className="modal-header"><div><span className="eyebrow">CHART STUDIES</span><h2 id="indicators-title">Indicators</h2></div><button className="icon-button" aria-label="Close indicators" onClick={onClose}><X size={20}/></button></header>
    <div className="indicator-layout"><aside className="indicator-library"><label className="indicator-search"><Search size={14}/><input aria-label="Search indicators" placeholder="Search 42 indicators" value={search} onChange={e => setSearch(e.target.value)}/></label>
      <div className="indicator-catalog">{definitions.filter(d => `${d.id} ${d.name} ${d.category}`.toLowerCase().includes(search.toLowerCase())).map(d => <button disabled={busy} className={selected?.id === d.id ? 'selected' : ''} key={d.id} onClick={() => choose(d)}><span>{d.name}<small>{label(d.category)}{d.volume_required && !hasVolume ? ' · volume unavailable' : ''}</small></span><Plus size={13}/></button>)}</div>
    </aside><section className="indicator-configuration">
      <h3>On this chart <span>{chart.indicators.length}</span></h3><div className="indicator-instances">{chart.indicators.map(i => {
        const definition = definitions.find(d => d.id === i.definition_id);
        return <div key={i.id}><span className="study-color" style={{ background: i.color }}/><button disabled={busy} className="study-name" onClick={() => definition && choose(definition, i)}><span>{definition?.name ?? i.definition_id}</span><Settings2 size={12}/></button><button disabled={busy} className="icon-button" aria-label={`${i.visible ? 'Hide' : 'Show'} ${definition?.name ?? i.definition_id}`} onClick={() => onChange(chart.indicators.map(x => x.id === i.id ? { ...x, visible: !x.visible } : x))}>{i.visible ? <Eye size={14}/> : <EyeOff size={14}/>}</button><button disabled={busy} className="icon-button" aria-label={`Remove ${definition?.name ?? i.definition_id}`} onClick={() => { onChange(chart.indicators.filter(x => x.id !== i.id)); if (editing === i.id) setEditing(null); }}><Trash2 size={13}/></button></div>;
      })}{!chart.indicators.length && <p className="small-note">Choose a study from the library to configure it.</p>}</div>
      {selected && <form onSubmit={e => { e.preventDefault(); void apply(); }}><h3>{editing ? 'Edit' : 'Add'} {selected.name}</h3><div className="indicator-fields">{Object.entries(selected.parameters).filter(([, control]) => control.kind !== 'fixed').map(([key, control]) => <label key={key}>{label(key)}
        {control.kind === 'choice' ? <select value={String(params[key] ?? control.default)} onChange={e => setParams({ ...params, [key]: key === 'ddof' ? Number(e.target.value) : e.target.value })}>{control.choices.map(c => <option key={c} value={c}>{c}</option>)}</select>
          : control.kind === 'boolean' ? <input type="checkbox" checked={Boolean(params[key])} onChange={e => setParams({ ...params, [key]: e.target.checked })}/>
            : control.kind === 'timestamp' ? <input required placeholder="2025-01-01T00:00:00Z" value={String(params[key] ?? '')} onChange={e => setParams({ ...params, [key]: e.target.value })}/>
              : <input required type="number" min={control.minimum ?? undefined} max={control.maximum ?? undefined} step={control.kind === 'integer' ? 1 : 'any'} value={String(params[key] ?? '')} onChange={e => setParams({ ...params, [key]: e.target.value === '' ? '' : Number(e.target.value) })}/>}
      </label>)}<label>Color<input type="color" value={color} onChange={e => setColor(e.target.value)}/></label><label>Line width<input type="number" min={1} max={5} value={width} onChange={e => setWidth(Number(e.target.value))}/></label><label>Pane<select value={pane} onChange={e => setPane(Number(e.target.value))}><option value={0}>Price overlay</option>{Array.from({ length: Math.max(3, pane, ...chart.indicators.map(i => i.pane))+1 }, (_, i) => i+1).map(i => <option key={i} value={i}>{i === 1 ? 'Volume / pane 1' : `Pane ${i}`}</option>)}</select></label></div>
        {selected.id === 'historical_volatility' && <p className="small-note">Set bars per year for this market and interval. The daily 24/7 preset is 365; a trading-session daily preset is 252.</p>}
        <details className="formula-details"><summary>Formula and calculation conventions</summary><p>{selected.formula}</p><p>{selected.warmup}</p><p>{selected.edge_cases}</p>{selected.notes.map(note => <p key={note}>{note}</p>)}<p>Contract {selected.contract_version} · completed source bars · display shifts do not move data availability</p>{selected.source_urls.map((url, i) => <a key={url} href={url} target="_blank" rel="noreferrer">Official reference {i+1} ↗ </a>)}</details>
        {error && <p className="error" role="alert">{error}</p>}<button className="primary" disabled={busy || !chart.dataset_id || (selected.volume_required && !hasVolume)} type="submit">{busy ? 'Checking…' : editing ? 'Update study' : 'Add study'}</button>
      </form>}
      <section className="indicator-templates"><h3>Templates</h3><div><input maxLength={80} aria-label="Indicator template name" placeholder="Template name" value={templateName} onChange={e => setTemplateName(e.target.value)}/><button disabled={!templateName.trim() || !chart.indicators.length} onClick={() => { onTemplates({ ...templates, [templateName.trim()]: chart.indicators }); setTemplateName(''); }}>Save template</button></div>{Object.entries(templates).map(([name, items]) => <div key={name}><span>{name} · {items.length} studies</span><button disabled={busy} onClick={() => onChange(items.map(i => ({ ...i, id: crypto.randomUUID() })))}>Apply {name}</button><button className="icon-button" aria-label={`Delete template ${name}`} onClick={() => onTemplates(Object.fromEntries(Object.entries(templates).filter(([key]) => key !== name)))}><Trash2 size={13}/></button></div>)}</section>
    </section></div>
  </dialog>;
}
