import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Copy, Download, MoreHorizontal, Pencil, Plus, Search, Trash2, Upload, X } from 'lucide-react';
import type { Dataset, DatasetView, Quote, Watchlist, WatchlistItem, Workspace } from './contracts';
import { download, formatPrice } from './api';
import { encodeCsv, parseCsv } from './csv';

interface Props {
  workspace: Workspace;
  datasets: Dataset[];
  views: Record<string, DatasetView>;
  quotes: Record<string, Quote>;
  selectedInstrument?: string;
  onChange: (watchlists: Watchlist[], activeId: string) => void;
  onSelect: (dataset: Dataset) => void;
  onVisible: (ids: string[]) => void;
}

export function Watchlists({ workspace: ws, datasets, views, quotes, selectedInstrument, onChange, onSelect, onVisible }: Props) {
  const list = ws.watchlists.find(w => w.id === ws.active_watchlist)!;
  const [menu, setMenu] = useState(false);
  const [editMode, setEditMode] = useState<'new' | 'rename' | 'section' | 'rename-section' | null>(null);
  const [originalSection, setOriginalSection] = useState('');
  const [name, setName] = useState('');
  const [filter, setFilter] = useState('');
  const sort = list.sort;
  const [scroll, setScroll] = useState(0);
  const [height, setHeight] = useState(300);
  const [notice, setNotice] = useState('');
  const [editingRow, setEditingRow] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const rowElements = useRef(new Map<string, HTMLDivElement>());
  const pendingFocus = useRef<string | null>(null);
  const instrumentMap = useMemo(() => {
    const mapping = new Map<string, Dataset>();
    datasets.forEach(d => { if (!mapping.has(d.instrument.id)) mapping.set(d.instrument.id, d); });
    return mapping;
  }, [datasets]);
  const update = (value: Watchlist) => onChange(ws.watchlists.map(w => w.id === value.id ? value : w), ws.active_watchlist);
  const replaceItems = (items: WatchlistItem[]) => update({ ...list, items });
  useEffect(() => {
    const element = viewport.current; if (!element) return;
    const observer = new ResizeObserver(entries => setHeight(entries[0].contentRect.height));
    observer.observe(element); return () => observer.disconnect();
  }, []);
  useEffect(() => { setScroll(0); if (viewport.current) viewport.current.scrollTop = 0; setNotice(''); }, [list.id, filter, sort]);

  function quoteInfo(id: string) {
    const data = instrumentMap.get(id);
    const bars = data ? views[data.id]?.bars : undefined;
    const live = quotes[id];
    const last = live?.price ?? bars?.at(-1)?.close;
    const previous = live ? bars?.at(-1)?.close : bars?.at(-2)?.close;
    return { last, change: last != null && previous != null ? last - previous : undefined,
      changePercent: last != null && previous ? (last / previous - 1) * 100 : undefined,
      status: live?.freshness ?? (bars?.length ? data?.source === 'fixture' ? 'Example' : 'Historical' : 'Unavailable') };
  }
  const items = list.items.filter(item => `${item.instrument_id} ${instrumentMap.get(item.instrument_id)?.instrument.name ?? ''}`.toLowerCase().includes(filter.toLowerCase()));
  const sections = ['', ...list.sections, ...list.items.map(i => i.section).filter(s => s && !list.sections.includes(s))].filter((s, i, a) => a.indexOf(s) === i);
  type Entry = { top: number; height: number; section: string; item?: WatchlistItem };
  const entries: Entry[] = []; let totalHeight = 0;
  for (const section of sections) {
    const group = items.filter(item => item.section === section);
    if (!group.length && (filter || !section)) continue;
    if (section) { entries.push({ top: totalHeight, height: 30, section }); totalHeight += 30; }
    if (sort !== 'manual') group.sort((a, b) => {
      if (sort === 'symbol') return (instrumentMap.get(a.instrument_id)?.instrument.symbol ?? a.instrument_id).localeCompare(instrumentMap.get(b.instrument_id)?.instrument.symbol ?? b.instrument_id);
      const key = sort as 'last' | 'change' | 'changePercent';
      return (quoteInfo(b.instrument_id)[key] ?? -Infinity) - (quoteInfo(a.instrument_id)[key] ?? -Infinity);
    });
    for (const item of group) { entries.push({ top: totalHeight, height: 62, section, item }); totalHeight += 62; }
  }
  const visible = entries.filter(e => e.top + e.height >= scroll - 62 && e.top <= scroll + height + 62);
  const visibleIds = visible.flatMap(e => e.item ? [e.item.instrument_id] : []).join('|');
  const visibleCallback = useRef(onVisible); visibleCallback.current = onVisible;
  useEffect(() => visibleCallback.current(visibleIds ? visibleIds.split('|') : []), [visibleIds]);
  useLayoutEffect(() => {
    const target = pendingFocus.current && rowElements.current.get(pendingFocus.current);
    if (target) { target.focus({ preventScroll: true }); pendingFocus.current = null; }
  }, [visibleIds]);

  function navigateList(event: React.KeyboardEvent<HTMLDivElement>) {
    if (!['ArrowUp', 'ArrowDown', 'Home', 'End', 'PageUp', 'PageDown'].includes(event.key)) return;
    if ((event.target as HTMLElement).matches('input, select, textarea')) return;
    const rows = entries.filter(entry => entry.item);
    if (!rows.length || !viewport.current) return;
    event.preventDefault();
    const currentId = (event.target as HTMLElement).closest<HTMLElement>('[data-watchlist-id]')?.dataset.watchlistId;
    const current = rows.findIndex(entry => entry.item!.instrument_id === currentId);
    const page = Math.max(1, Math.floor(height/62));
    const destination = event.key === 'Home' ? 0 : event.key === 'End' ? rows.length-1
      : Math.max(0, Math.min(rows.length-1, current + (event.key === 'ArrowUp' ? -1 : event.key === 'ArrowDown' ? 1 : event.key === 'PageUp' ? -page : page)));
    const target = rows[destination], id = target.item!.instrument_id;
    const top = viewport.current.scrollTop;
    const nextScroll = target.top < top ? target.top : target.top + target.height > top + height ? target.top + target.height - height : top;
    pendingFocus.current = id;
    viewport.current.scrollTop = nextScroll; setScroll(viewport.current.scrollTop);
    const mounted = rowElements.current.get(id);
    if (mounted) { mounted.focus({ preventScroll: true }); pendingFocus.current = null; }
  }

  function move(id: string, direction: number) {
    const original = list.items.findIndex(i => i.instrument_id === id);
    const candidates = list.items.map((item, index) => ({ item, index })).filter(e => e.item.section === list.items[original].section);
    const position = candidates.findIndex(e => e.index === original);
    const destination = candidates[position + direction]?.index;
    if (destination == null) return;
    const next = [...list.items]; [next[original], next[destination]] = [next[destination], next[original]];
    replaceItems(next);
  }

  function moveSection(section: string, direction: number) {
    const next = sections.filter(Boolean), index = next.indexOf(section);
    const destination = index + direction;
    if (destination < 0 || destination >= next.length) return;
    [next[index], next[destination]] = [next[destination], next[index]];
    update({ ...list, sections: next });
  }

  async function importList(selected: File) {
    try {
      if (selected.size > 5_000_000) throw new Error('Watchlist CSV must be smaller than 5 MB.');
      const [header, ...rows] = parseCsv(await selected.text());
      const idColumn = header?.indexOf('instrument_id'), sectionColumn = header?.indexOf('section');
      if (idColumn == null || idColumn < 0) throw new Error('CSV needs an instrument_id column.');
      if (new Set(header).size !== header.length) throw new Error('CSV column names must be unique.');
      const seen = new Set(list.items.map(i => i.instrument_id));
      const additions: WatchlistItem[] = []; let duplicates = 0, unknown = 0;
      for (const [index, row] of rows.entries()) {
        if (row.every(v => !v.trim())) continue;
        const id = row[idColumn]?.trim();
        if (!id || id.length > 160) throw new Error(`Row ${index + 2}: invalid instrument identity.`);
        if (seen.has(id)) { duplicates++; continue; }
        seen.add(id);
        if (!instrumentMap.has(id)) unknown++;
        const section = sectionColumn >= 0 ? row[sectionColumn]?.trim() ?? '' : '';
        if (section.length > 100) throw new Error(`Row ${index + 2}: section name exceeds 100 characters.`);
        additions.push({ schema_version: 1, instrument_id: id, section });
      }
      update({ ...list, items: [...list.items, ...additions], sections: [...new Set([...list.sections, ...additions.map(i => i.section).filter(Boolean)])] });
      setNotice(`Added ${additions.length}; skipped ${duplicates} duplicates. ${unknown} identities have no local dataset and remain unavailable.`);
    } catch (error) { setNotice(String(error)); }
  }

  return <>
    <div className="watchlist-title"><select aria-label="Active watchlist" value={list.id} onChange={e => onChange(ws.watchlists, e.target.value)}>{ws.watchlists.map(w => <option value={w.id} key={w.id}>{w.name}</option>)}</select><div className="relative"><button className="icon-button" aria-label="Manage watchlists" aria-expanded={menu} onClick={() => setMenu(!menu)}><MoreHorizontal size={18}/></button>{menu && <div className="popover watchlist-menu">
      <button onClick={() => { setEditMode('new'); setName(''); setMenu(false); }}><Plus size={13}/>New list</button><button onClick={() => { setEditMode('rename'); setName(list.name); setMenu(false); }}>Rename list</button><button onClick={() => { const id = crypto.randomUUID(); onChange([...ws.watchlists, { ...list, id, name: `${list.name} copy` }], id); setMenu(false); }}><Copy size={13}/>Duplicate list</button><button onClick={() => { setEditMode('section'); setName(''); setMenu(false); }}>Add section</button>
      <button onClick={() => { download(`${list.name}.csv`, encodeCsv([['instrument_id', 'section', 'symbol', 'exchange', 'currency'], ...list.items.map(item => { const i = instrumentMap.get(item.instrument_id)?.instrument; return [item.instrument_id, item.section, i?.symbol, i?.exchange, i?.quote_currency]; })]), 'text/csv'); setMenu(false); }}><Download size={13}/>Export CSV</button><button onClick={() => { file.current?.click(); setMenu(false); }}><Upload size={13}/>Import CSV</button>
      <button disabled={ws.watchlists.length === 1} onClick={() => { const remaining = ws.watchlists.filter(w => w.id !== list.id); onChange(remaining, remaining[0].id); setMenu(false); }}><Trash2 size={13}/>Delete list</button>
    </div>}</div><input ref={file} type="file" accept=".csv,text/csv" aria-label="Watchlist CSV" hidden onChange={e => { const selected = e.target.files?.[0]; if (selected) void importList(selected); e.target.value = ''; }}/></div>
    {editMode && <form className="new-list" onSubmit={e => {
      e.preventDefault(); const text = name.trim(); if (!text) return;
      if (editMode === 'new') { const id = crypto.randomUUID(); onChange([...ws.watchlists, { schema_version: 1, id, name: text, items: [], sections: [], sort: 'manual' }], id); }
      if (editMode === 'rename') update({ ...list, name: text });
      if (editMode === 'section') update({ ...list, sections: [...new Set([...list.sections, text])] });
      if (editMode === 'rename-section') {
        if (text !== originalSection && sections.includes(text)) { setNotice('That section name is already in use.'); return; }
        update({ ...list, sections: sections.filter(Boolean).map(s => s === originalSection ? text : s), items: list.items.map(i => i.section === originalSection ? { ...i, section: text } : i) });
      }
      setEditMode(null);
    }}><input autoFocus maxLength={100} aria-label={editMode?.includes('section') ? 'Section name' : 'Watchlist name'} value={name} onChange={e => setName(e.target.value)} placeholder={editMode?.includes('section') ? 'Section name' : 'List name'}/><button type="submit">Save</button><button aria-label="Cancel name edit" type="button" onClick={() => setEditMode(null)}><X size={13}/></button></form>}
    <div className="watchlist-filter"><Search size={12}/><input aria-label="Search watchlist" placeholder="Filter this list" value={filter} onChange={e => setFilter(e.target.value)}/></div>
    <div className="watchlist-columns"><span>{items.length} INSTRUMENTS</span><select aria-label="Watchlist sort" value={sort} onChange={e => update({ ...list, sort: e.target.value as Watchlist['sort'] })}><option value="manual">Manual order</option><option value="symbol">Symbol A–Z</option><option value="last">Last ↓</option><option value="change">Change ↓</option><option value="changePercent">Change % ↓</option></select></div>
    <div className="watchlist-items virtual-list" ref={viewport} onScroll={e => setScroll(e.currentTarget.scrollTop)} role="list" tabIndex={0} onKeyDown={navigateList} aria-label="Watchlist instruments" aria-description="Use Up and Down, Home and End, or Page Up and Page Down to navigate all instruments. Enter selects an available instrument. Tab reaches its actions."><div style={{ height: totalHeight, position: 'relative' }}>
      {visible.map(entry => entry.item ? (() => {
        const item = entry.item!, data = instrumentMap.get(item.instrument_id), quote = quoteInfo(item.instrument_id);
        const change = quote.changePercent;
        return <div key={item.instrument_id} role="listitem" tabIndex={-1} data-watchlist-id={item.instrument_id}
          aria-label={`${data?.instrument.symbol ?? item.instrument_id}, ${data?.instrument.exchange ?? 'dataset unavailable'}, ${quote.status}`}
          ref={node => { if (node) rowElements.current.set(item.instrument_id, node); else rowElements.current.delete(item.instrument_id); }}
          onKeyDown={event => { if (event.target === event.currentTarget && event.key === 'Enter') { event.preventDefault(); if (data) onSelect(data); else setNotice('This instrument has no local dataset. Connect or import its data before selecting it.'); } }}
          className={`watchlist-row ${selectedInstrument === item.instrument_id ? 'active' : ''}`} style={{ position: 'absolute', top: entry.top, height: entry.height, width: '100%' }}>
          <button className="watchlist-select" disabled={!data} onClick={() => data && onSelect(data)} aria-label={`${data?.instrument.symbol ?? item.instrument_id}, ${data?.instrument.exchange ?? 'dataset unavailable'}, ${quote.status}`}><span><b>{data?.instrument.symbol ?? item.instrument_id}</b><small>{data ? `${data.instrument.exchange} · ${data.instrument.quote_currency}` : 'Dataset unavailable'}</small></span><span><b>{formatPrice(quote.last)}</b><small>{change == null ? quote.status : `${change >= 0 ? '+' : ''}${change.toFixed(2)}% · ${quote.status}`}</small></span></button>
          <div className="row-actions"><button className="icon-button" disabled={sort !== 'manual'} aria-label={`Move ${data?.instrument.symbol ?? item.instrument_id} up`} onClick={() => move(item.instrument_id, -1)}><ArrowUp size={12}/></button><button className="icon-button" disabled={sort !== 'manual'} aria-label={`Move ${data?.instrument.symbol ?? item.instrument_id} down`} onClick={() => move(item.instrument_id, 1)}><ArrowDown size={12}/></button><button className="icon-button" aria-label={`Choose section for ${data?.instrument.symbol ?? item.instrument_id}`} onClick={() => setEditingRow(editingRow === item.instrument_id ? null : item.instrument_id)}><MoreHorizontal size={12}/></button><button className="icon-button" aria-label={`Remove ${data?.instrument.symbol ?? item.instrument_id} from watchlist`} onClick={() => replaceItems(list.items.filter(i => i.instrument_id !== item.instrument_id))}><X size={12}/></button></div>
          {editingRow === item.instrument_id && <select className="section-select" aria-label={`Section for ${data?.instrument.symbol ?? item.instrument_id}`} value={item.section} onChange={e => { replaceItems(list.items.map(i => i.instrument_id === item.instrument_id ? { ...i, section: e.target.value } : i)); setEditingRow(null); }}>{sections.map(s => <option key={s} value={s}>{s || 'No section'}</option>)}</select>}
        </div>;
      })() : <div className="watchlist-section" key={`section:${entry.section}`} style={{ position: 'absolute', top: entry.top, height: entry.height, width: '100%' }}><span>{entry.section}</span><button className="icon-button" aria-label={`Move section ${entry.section} up`} onClick={() => moveSection(entry.section, -1)}><ArrowUp size={11}/></button><button className="icon-button" aria-label={`Move section ${entry.section} down`} onClick={() => moveSection(entry.section, 1)}><ArrowDown size={11}/></button><button className="icon-button" aria-label={`Rename section ${entry.section}`} onClick={() => { setOriginalSection(entry.section); setName(entry.section); setEditMode('rename-section'); }}><Pencil size={11}/></button><button className="icon-button" aria-label={`Remove section ${entry.section}`} onClick={() => update({ ...list, sections: list.sections.filter(s => s !== entry.section), items: list.items.map(i => i.section === entry.section ? { ...i, section: '' } : i) })}><X size={11}/></button></div>)}
    </div>{!entries.length && <p className="panel-empty">{filter ? 'No matching instruments.' : 'A place for the instruments you follow.'}</p>}</div>
    <label className="watchlist-add"><Plus size={14}/><select aria-label="Add instrument to watchlist" value="" onChange={e => { if (e.target.value) replaceItems([...list.items, { schema_version: 1, instrument_id: e.target.value, section: '' }]); }}><option value="">Add from datasets</option>{[...instrumentMap.values()].filter(d => !list.items.some(i => i.instrument_id === d.instrument.id)).map(d => <option value={d.instrument.id} key={d.instrument.id}>{d.instrument.symbol} · {d.instrument.exchange}</option>)}</select></label>
    {notice && <p className="watchlist-notice" role="status">{notice}</p>}
  </>;
}
