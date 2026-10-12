import { useModal } from './useModal';
import { useState } from 'react';
import { Play, X } from 'lucide-react';
import type { AccountView, Dataset, ResearchJob, ResearchRequest, ScriptAnalysis, StrategyDefinition } from './contracts';
import { api } from './api';

export function RunDialog({ script, analysis, datasets, activeDataset, onClose, onRun, replay }: {
  script: StrategyDefinition; analysis: ScriptAnalysis; datasets: Dataset[]; activeDataset?: string;
  onClose: () => void; onRun: (job: ResearchJob) => void; replay?: AccountView | null;
}) {
  const dialog = useModal();
  const [selection, setSelection] = useState<string[]>(replay?.account.dataset_ids ?? (activeDataset ? [activeDataset] : []));
  const [parameters, setParameters] = useState<Record<string, string | number | boolean>>(
    Object.fromEntries(Object.entries(analysis.parameters).map(([key, value]) => [key, value.default])));
  const [name, setName] = useState(script.name+(replay ? ' replay to cursor' : ' run'));
  const [capital, setCapital] = useState(replay?.account.settings.initial_capital ?? '100000');
  const [currency, setCurrency] = useState(replay?.account.settings.reporting_currency ?? 'USD');
  const [fees, setFees] = useState(replay?.account.settings.fee_bps ?? '0'), [fixedFee, setFixedFee] = useState(replay?.account.settings.fee_per_order ?? '0'), [slippage, setSlippage] = useState(replay?.account.settings.slippage_bps ?? '0');
  const [start, setStart] = useState(replay ? new Date(replay.first_time*1000).toISOString().slice(0, 19) : ''), [end, setEnd] = useState(replay ? new Date(replay.account.cursor*1000).toISOString().slice(0, 19) : '');
  const [shorting, setShorting] = useState(replay?.account.settings.allow_short ?? true), [fixtures, setFixtures] = useState(replay?.account.settings.allow_fixture_data ?? false);
  const [deadline, setDeadline] = useState(300), [memory, setMemory] = useState(1024), [seed, setSeed] = useState(replay?.account.settings.seed ?? 0);
  const [actions, setActions] = useState(JSON.stringify(replay?.account.actions ?? []));
  const [coverage, setCoverage] = useState<ResearchRequest['settings']['corporate_action_coverage']>(replay?.account.settings.corporate_action_coverage ?? 'unknown');
  const [maxAge, setMaxAge] = useState(replay?.account.settings.fx_max_age_seconds?.toString() ?? '');
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  async function run() {
    setError(''); setBusy(true);
    try {
      const selected = datasets.filter(d => selection.includes(d.id));
      if (!selection.length) throw new Error('Select at least one dataset.');
      if (new Set(selected.map(d => d.instrument.id)).size !== selected.length) throw new Error('Select one dataset per instrument.');
      const request: ResearchRequest = { schema_version: 1, name, script, dataset_ids: selection,
        parameters, actions: JSON.parse(actions), limits: { schema_version: 1, deadline_seconds: deadline, memory_mb: memory },
        settings: { schema_version: 1, initial_capital: capital, reporting_currency: currency, fee_bps: fees,
          fee_per_order: fixedFee, slippage_bps: slippage, allow_short: shorting, allow_fixture_data: fixtures,
          seed, start: start ? Date.parse(start+'Z')/1000 : null, end: end ? Date.parse(end+'Z')/1000 : null,
          fx_max_age_seconds: maxAge ? Number(maxAge) : null, corporate_action_coverage: coverage } };
      onRun(await api<ResearchJob>('/research', { method: 'POST', body: JSON.stringify(request) }));
    } catch (err) { setError(String(err)); setBusy(false); }
  }
  return <dialog ref={dialog} className="run-dialog" onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <form onSubmit={event => { event.preventDefault(); void run(); }}>
      <header><div><h2>{replay ? 'Run strategy to replay cursor' : 'Run Python research'}</h2><p>The current editor source and selected inputs will be saved with this run.</p></div><button type="button" className="icon-button" disabled={busy} aria-label="Close run settings" onClick={onClose}><X size={18}/></button></header>
      <div className="run-body"><section><label>Run name<input required maxLength={120} value={name} onChange={e => setName(e.target.value)}/></label>
        <h3>Data universe</h3><p className="small-note">One interval and source per instrument. Include currency pairs needed to value foreign positions.</p>
        <div className="run-datasets">{datasets.map(d => <label key={d.id}><input type="checkbox" checked={selection.includes(d.id)} onChange={e => setSelection(e.target.checked ? [...selection, d.id] : selection.filter(id => id !== d.id))}/><span><b>{d.instrument.symbol}</b> · {d.instrument.exchange} · {d.interval}<small>{d.source}/{d.feed} · {d.instrument.quote_currency} · {d.row_count.toLocaleString()} bars · {d.id.slice(0, 8)}</small></span></label>)}</div>
        <div className="run-fields"><label>Start · UTC<input aria-label="Run start UTC" type="datetime-local" value={start} onChange={e => setStart(e.target.value)}/></label><label>End · UTC<input aria-label="Run end UTC" disabled={!!replay} type="datetime-local" step="1" value={end} onChange={e => setEnd(e.target.value)}/></label></div><p className="small-note">{replay ? 'This independent strategy run ends at the replay cursor, using the replay universe and account settings. Manual account commands are separate.' : 'Blank dates use available history. Earlier bars warm up indicators; positions start empty.'}</p>
        <h3>Script parameters</h3>{Object.entries(analysis.parameters).map(([key, spec]) => <label className="script-parameter" key={key}>{key}{spec.type === 'bool' ? <input type="checkbox" checked={Boolean(parameters[key])} onChange={e => setParameters({ ...parameters, [key]: e.target.checked })}/> : spec.choices.length ? <select aria-label={`Parameter ${key}`} value={String(parameters[key])} onChange={e => setParameters({ ...parameters, [key]: spec.choices.find(v => String(v) === e.target.value)! })}>{spec.choices.map(value => <option key={String(value)}>{String(value)}</option>)}</select> : <input aria-label={`Parameter ${key}`} required type={spec.type === 'str' ? 'text' : 'number'} min={spec.minimum ?? undefined} max={spec.maximum ?? undefined} step={spec.type === 'int' ? 1 : 'any'} value={String(parameters[key])} onChange={e => setParameters({ ...parameters, [key]: spec.type === 'str' ? e.target.value : Number(e.target.value) })}/>}<small>{spec.description}</small></label>)}
      </section><section><h3>Portfolio and execution</h3><div className="run-fields"><label>Initial capital<input aria-label="Initial capital" type="number" required min="0.01" step="any" value={capital} onChange={e => setCapital(e.target.value)}/></label><label>Reporting currency<input required pattern="[A-Z]{3,12}" value={currency} onChange={e => setCurrency(e.target.value.toUpperCase())}/></label><label>Fee · basis points<input type="number" required min="0" max="10000" step="any" value={fees} onChange={e => setFees(e.target.value)}/></label><label>Fixed fee · quote currency<input type="number" required min="0" step="any" value={fixedFee} onChange={e => setFixedFee(e.target.value)}/></label><label>Slippage · basis points<input type="number" required min="0" max="9999" step="any" value={slippage} onChange={e => setSlippage(e.target.value)}/></label><label>Random seed<input type="number" required step="1" value={seed} onChange={e => setSeed(Number(e.target.value))}/></label></div>
        <p className="notice">Zero costs are an explicit assumption. Orders use completed-bar signals and the next eligible opening or touch. Ambiguous bracket exits resolve stop first.</p>
        <label className="check-row"><input type="checkbox" checked={shorting} onChange={e => setShorting(e.target.checked)}/>Allow shorts with 100% collateral and restricted proceeds</label><label className="check-row"><input type="checkbox" checked={fixtures} onChange={e => setFixtures(e.target.checked)}/>Allow labeled synthetic demonstration data</label>
        <h3>Worker limits</h3><div className="run-fields"><label>Deadline · seconds<input type="number" required min="1" max="3600" value={deadline} onChange={e => setDeadline(Number(e.target.value))}/></label><label>Memory · MB<input type="number" required min="128" max="8192" value={memory} onChange={e => setMemory(Number(e.target.value))}/></label></div>
        <details><summary>Currency age and corporate actions</summary><label>Maximum FX age · seconds<input type="number" min="1" value={maxAge} onChange={e => setMaxAge(e.target.value)} placeholder="Use latest available and report its age"/></label><label>Corporate-action coverage<select value={coverage} onChange={e => setCoverage(e.target.value as typeof coverage)}><option value="unknown">Unknown</option><option value="supplied-partial">Supplied, partial</option><option value="supplied-complete">Supplied, complete</option></select></label><label>Supplied events · JSON<textarea value={actions} onChange={e => setActions(e.target.value)} aria-label="Corporate actions JSON"/></label><p className="small-note">Each event needs instrument_id, time (UTC seconds), kind (split or dividend), value, and source. Dividend time is cash-effective.</p></details>
      </section></div>
      {error && <p className="error-banner" role="alert">{error}</p>}<footer><p>Run trusted Python only. Workers are separate processes, with access to local files.</p><button type="submit" className="primary-button" disabled={busy}>{busy ? 'Saving inputs…' : <><Play size={14}/>Run</>}</button></footer>
    </form></dialog>;
}
