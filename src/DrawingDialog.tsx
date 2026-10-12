import { useModal } from './useModal';
import { useEffect, useState } from 'react';
import { Copy, Eye, EyeOff, LockKeyhole, Trash2, UnlockKeyhole, X } from 'lucide-react';
import type { Bar, Drawing } from './contracts';
import { drawingTools } from './drawingGeometry';

interface Props {
  drawings: Drawing[];
  instrumentId?: string;
  bars?: Bar[];
  selected: string | null;
  onSelect: (id: string | null) => void;
  onChange: (drawings: Drawing[]) => void;
  onClose: () => void;
}
export function DrawingDialog({ drawings, instrumentId, bars, selected, onSelect, onChange, onClose }: Props) {
  const dialog = useModal();
  const [draft, setDraft] = useState<Drawing | null>(null);
  const [levels, setLevels] = useState('');
  const [error, setError] = useState('');
  const [newKind, setNewKind] = useState<Drawing['kind']>('trend');
  const [anchorPage, setAnchorPage] = useState(0);
  const object = drawings.find(d => d.id === selected);
  useEffect(() => { setDraft(object ? structuredClone(object) : null); setLevels(object?.levels.join(', ') ?? ''); setError(''); setAnchorPage(0); }, [object]);
  const name = (d: Drawing) => drawingTools.find(t => t.kind === d.kind)?.name ?? d.kind;
  const update = (value: Drawing) => onChange(drawings.map(d => d.id === value.id ? value : d));
  function create() {
    if (!instrumentId || !bars?.length) return;
    const count = Math.max(2, drawingTools.find(t => t.kind === newKind)!.anchors);
    const sample = bars.slice(-count);
    const needed = drawingTools.find(t => t.kind === newKind)!.anchors || 2;
    const anchors: Drawing['anchors'] = Array.from({ length: needed }, (_, i) => {
      const bar = sample[Math.min(i, sample.length - 1)];
      return { schema_version: 1, time: bar.start, price: bar.close };
    });
    if (newKind.endsWith('-position')) {
      const entry = anchors[0].price, direction = newKind === 'long-position' ? 1 : -1;
      anchors[1].price = entry * (1 - direction * .01);
      anchors[2].price = entry * (1 + direction * .02);
    }
    const value: Drawing = { schema_version: 1, id: crypto.randomUUID(), kind: newKind, instrument_id: instrumentId,
      anchors, color: '#70b8f0', opacity: 1, width: 2, label: newKind === 'text' ? 'Text' : '',
      levels: newKind === 'fib-extension' ? [0, .618, 1, 1.618, 2.618] : [0, .236, .382, .5, .618, .786, 1],
      visible: true, locked: false, quantity: '1' };
    onChange([...drawings, value]); onSelect(value.id);
  }
  return <dialog className="modal drawing-dialog" ref={dialog} onCancel={onClose} aria-labelledby="objects-title">
    <header><div><span className="eyebrow">TIME & PRICE ANCHORS</span><h2 id="objects-title">Drawing objects</h2></div><button className="icon-button" aria-label="Close drawing objects" onClick={onClose}><X size={18}/></button></header>
    <div className="drawing-create"><label>New drawing type<select value={newKind} onChange={e => setNewKind(e.target.value as Drawing['kind'])}>{drawingTools.map(tool => <option key={tool.kind} value={tool.kind}>{tool.name}</option>)}</select></label><button disabled={!instrumentId || !bars?.length} onClick={create}>Create drawing</button><p className="small-note">Starts at recent visible bars. Edit the UTC times and prices below to place it precisely.</p></div>
    <div className="drawing-object-layout"><section className="drawing-object-list">{drawings.filter(d => d.instrument_id === instrumentId).map(d => <div key={d.id} className={d.id === selected ? 'selected' : ''}>
      <button className="object-name" onClick={() => onSelect(d.id)}><span className="study-color" style={{ background: d.color }}/>{d.label || name(d)}</button>
      <button className="icon-button" aria-label={`${d.visible ? 'Hide' : 'Show'} drawing ${name(d)}`} onClick={() => update({ ...d, visible: !d.visible })}>{d.visible ? <Eye size={13}/> : <EyeOff size={13}/>}</button>
      <button className="icon-button" aria-label={`${d.locked ? 'Unlock' : 'Lock'} drawing ${name(d)}`} onClick={() => update({ ...d, locked: !d.locked })}>{d.locked ? <LockKeyhole size={13}/> : <UnlockKeyhole size={13}/>}</button>
      <button className="icon-button" aria-label={`Duplicate drawing ${name(d)}`} onClick={() => { const copy = { ...structuredClone(d), id: crypto.randomUUID(), label: d.label ? d.label+' copy' : name(d)+' copy' }; onChange([...drawings, copy]); onSelect(copy.id); }}><Copy size={13}/></button>
      <button className="icon-button" aria-label={`Delete drawing ${name(d)}`} onClick={() => { onChange(drawings.filter(x => x.id !== d.id)); if (selected === d.id) onSelect(null); }}><Trash2 size={13}/></button>
    </div>)}{!drawings.some(d => d.instrument_id === instrumentId) && <p className="small-note">Choose a drawing tool, then place its anchors on the price chart.</p>}</section>
    <section className="drawing-object-settings">{draft ? <form onSubmit={event => {
      event.preventDefault(); setError('');
      const parsed = levels.split(',').filter(s => s.trim()).map(Number);
      if (parsed.length > 30 || parsed.some(v => !Number.isFinite(v))) { setError('Enter up to 30 finite, comma-separated levels.'); return; }
      if (draft.anchors.some(a => !Number.isFinite(a.time) || !Number.isFinite(a.price) || a.price <= 0)) { setError('Anchors need valid UTC times and positive prices.'); return; }
      if (!Number.isFinite(Number(draft.quantity)) || Number(draft.quantity) <= 0) { setError('Quantity must be positive.'); return; }
      update({ ...draft, levels: parsed });
    }}><h3>{name(draft)}</h3><div className="indicator-fields"><label>Label<input maxLength={1000} value={draft.label} onChange={e => setDraft({ ...draft, label: e.target.value })}/></label><label>Color<input type="color" value={draft.color} onChange={e => setDraft({ ...draft, color: e.target.value })}/></label><label>Opacity<input type="number" min={0} max={1} step={.05} value={draft.opacity} onChange={e => setDraft({ ...draft, opacity: Number(e.target.value) })}/></label><label>Width<input type="number" min={1} max={8} step={1} value={draft.width} onChange={e => setDraft({ ...draft, width: Number(e.target.value) })}/></label>
      {draft.kind.startsWith('fib-') && <label>Levels<input value={levels} onChange={e => setLevels(e.target.value)}/></label>}
      {draft.kind.endsWith('-position') && <label>Quantity<input type="number" min={Number.MIN_VALUE} step="any" value={draft.quantity} onChange={e => setDraft({ ...draft, quantity: e.target.value })}/></label>}
    </div><details open={draft.anchors.length <= 3}><summary>Anchors · UTC</summary><div className="anchor-fields">{draft.anchors.slice(anchorPage*100, (anchorPage+1)*100).map((a, localIndex) => { const i = anchorPage*100 + localIndex; return <div key={i}><span>{i+1}</span><input required aria-label={`Anchor ${i+1} time`} type="datetime-local" step="1" value={new Date(a.time*1000).toISOString().slice(0, 19)} onChange={e => { const time = Date.parse(e.target.value+'Z')/1000; if (Number.isFinite(time)) setDraft({ ...draft, anchors: draft.anchors.map((x, n) => n === i ? { ...x, time } : x) }); }}/><input required aria-label={`Anchor ${i+1} price`} type="number" min={Number.MIN_VALUE} step="any" value={a.price} onChange={e => setDraft({ ...draft, anchors: draft.anchors.map((x, n) => n === i ? { ...x, price: Number(e.target.value) } : x) })}/></div>; })}</div>{draft.anchors.length > 100 && <div className="drawing-anchor-pages"><button type="button" disabled={!anchorPage} onClick={() => setAnchorPage(anchorPage-1)}>Previous anchors</button><span>Page {anchorPage+1} of {Math.ceil(draft.anchors.length/100)}</span><button type="button" disabled={(anchorPage+1)*100 >= draft.anchors.length} onClick={() => setAnchorPage(anchorPage+1)}>Next anchors</button></div>}{(draft.kind === "path" || draft.kind === "brush") && <div className="drawing-anchor-pages"><button type="button" disabled={draft.anchors.length >= 10000} onClick={() => { setDraft({ ...draft, anchors: [...draft.anchors, { ...draft.anchors.at(-1)! }] }); setAnchorPage(Math.floor(draft.anchors.length/100)); }}>Add anchor</button><button type="button" disabled={draft.anchors.length <= 2} onClick={() => { setDraft({ ...draft, anchors: draft.anchors.slice(0,-1) }); setAnchorPage(Math.min(anchorPage, Math.floor((draft.anchors.length-2)/100))); }}>Remove last anchor</button></div>}</details>
      {draft.kind.endsWith('-position') && <p className="small-note">Entry, stop, target order. Gross risk and reward use the instrument’s price tick, quantity step, and quote currency; fees and slippage are excluded.</p>}
      {error && <p className="error" role="alert">{error}</p>}<button type="submit" className="primary">Save drawing</button>
    </form> : <p className="small-note">Select an object to edit its appearance and anchors. Locked objects can be edited here; dragging them on the chart is disabled.</p>}</section></div>
  </dialog>;
}
