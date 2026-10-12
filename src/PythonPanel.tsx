import { useEffect, useRef, useState } from 'react';
import Editor, { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api';
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';
import 'monaco-editor/esm/vs/basic-languages/python/python.contribution';
import { Copy, Download, History, Plus, Save, Trash2, Upload, Play } from 'lucide-react';
import type { AccountView, Dataset, ResearchJob, ScriptAnalysis, StrategyDefinition } from './contracts';
import { api, download } from './api';
import { RunDialog } from './RunDialog';

(self as typeof self & { MonacoEnvironment: { getWorker: () => Worker } }).MonacoEnvironment = { getWorker: () => new EditorWorker() };
loader.config({ monaco });

const startingSource = `"""A strategy receives only completed bars through its context."""
PARAMETERS = {
    "length": {"type": "int", "default": 20, "minimum": 1, "maximum": 500}
}

def initialize(ctx):
    ctx.log("Initialized at", ctx.clock)

def on_bars(ctx, bars):
    for instrument_id, bar in bars.items():
        ctx.log(instrument_id, bar.close)

def finalize(ctx):
    ctx.log("Finished at", ctx.clock)
`;

export function PythonPanel({ theme, datasets, activeDataset, onRun, replay }: { theme: 'dark' | 'light'; datasets: Dataset[]; activeDataset?: string; onRun: (job: ResearchJob) => void; replay?: AccountView | null }) {
  const [runOpen, setRunOpen] = useState(false);
  const [tabMovesFocus, setTabMovesFocus] = useState(true);
  const tabModeControl = useRef<HTMLInputElement>(null);
  const [scripts, setScripts] = useState<StrategyDefinition[]>([]);
  const [draft, setDraft] = useState<StrategyDefinition | null>(null);
  const [analysis, setAnalysis] = useState<ScriptAnalysis | null>(null);
  const [error, setError] = useState('');
  const [savedSource, setSavedSource] = useState('');
  const [busy, setBusy] = useState(false);
  const [versions, setVersions] = useState<StrategyDefinition[] | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const editor = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const dirty = !!draft && JSON.stringify(draft) !== savedSource;
  const storageKey = 'market-workbench-python-draft';
  useEffect(() => {
    let mounted = true;
    api<StrategyDefinition[]>('/scripts').then(values => {
      if (!mounted) return;
      setScripts(values);
      try {
        const stored = localStorage.getItem(storageKey);
        if (stored) {
          const restored = JSON.parse(stored);
          if (!restored || typeof restored.source !== 'string' || typeof restored.name !== 'string' || typeof restored.id !== 'string' || !['strategy', 'indicator'].includes(restored.kind)) throw new Error('Invalid stored draft');
          setDraft(restored);
          const saved = values.find(s => s.id === restored.id);
          if (saved) setSavedSource(JSON.stringify(saved));
          return;
        }
      } catch { setError('The local draft could not be restored. Saved script versions remain available.'); }
      if (values.length) { setDraft(values[0]); setSavedSource(JSON.stringify(values[0])); }
    }).catch(e => mounted && setError(String(e)));
    return () => { mounted = false; };
  }, []);
  useEffect(() => {
    if (draft) localStorage.setItem(storageKey, JSON.stringify(draft));
    const controller = new AbortController();
    setAnalysis(null);
    const timer = setTimeout(() => {
      if (!draft) return;
      api<ScriptAnalysis>('/scripts/analyze', { method: 'POST', signal: controller.signal, body: JSON.stringify(draft) })
        .then(value => { if (!controller.signal.aborted) setAnalysis(value); })
        .catch(e => { if (!controller.signal.aborted) setError(String(e)); });
    }, 450);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [draft]);
  useEffect(() => {
    const model = editor.current?.getModel(); if (!model) return;
    monaco.editor.setModelMarkers(model, 'python-static-analysis', (analysis?.diagnostics ?? []).map(d => ({
      startLineNumber: d.line, endLineNumber: d.line, startColumn: d.column, endColumn: d.column+1,
      severity: d.severity === 'error' ? monaco.MarkerSeverity.Error : monaco.MarkerSeverity.Warning, message: d.message,
    })));
  }, [analysis]);
  function newScript(source = startingSource, name = 'Untitled strategy') {
    setError(''); setVersions(null); setSavedSource('');
    setDraft({ schema_version: 1, id: crypto.randomUUID(), name, source, kind: 'strategy', revision: 0, parameters: {}, subscriptions: [] });
  }
  async function save() {
    if (!draft) return;
    setBusy(true); setError('');
    const value = draft;
    try {
      const saved = await api<StrategyDefinition>(`/scripts/${value.id}`, { method: 'PUT', body: JSON.stringify(value) });
      setScripts(previous => [saved, ...previous.filter(s => s.id !== saved.id)]);
      setSavedSource(JSON.stringify(saved));
      setDraft(previous => previous?.id === saved.id ? { ...previous, revision: saved.revision } : previous);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  function canSwitch() {
    if (!dirty) return true;
    setError('Save this draft before switching scripts. Export it if you want a separate copy.');
    return false;
  }
  return <section className="python-panel" aria-label="Python editor">
    <div className="python-toolbar"><button className="primary-button" disabled={!draft || !analysis?.valid || busy} onClick={() => setRunOpen(true)}><Play size={13}/>Run settings</button><select aria-label="Saved Python script" value={draft?.id ?? ''} onChange={e => {
      if (!canSwitch()) return;
      const selected = scripts.find(s => s.id === e.target.value); if (selected) { setDraft(selected); setSavedSource(JSON.stringify(selected)); setVersions(null); setError(''); }
    }}><option value="">Select a saved script</option>{draft && !scripts.some(s => s.id === draft.id) && <option value={draft.id}>{draft.name} · draft</option>}{scripts.map(s => <option key={s.id} value={s.id}>{s.name} · v{s.revision}</option>)}</select>
      <button onClick={() => { if (canSwitch()) newScript(); }}><Plus size={13}/>New</button><button disabled={!draft || busy} onClick={() => { if (draft && canSwitch()) { newScript(draft.source, draft.name+' copy'); setDraft(value => value ? { ...value, kind: draft.kind } : value); } }}><Copy size={13}/>Duplicate</button>
      <button disabled={!draft || busy || !draft.name.trim()} onClick={() => void save()}><Save size={13}/>Save version</button><button disabled={!draft?.revision} onClick={async () => { if (!draft) return; try { setVersions(versions ? null : await api<StrategyDefinition[]>(`/scripts/${draft.id}/versions`)); } catch (e) { setError(String(e)); } }}><History size={13}/>Versions</button><span className="toolbar-spacer"/>
      <button className="icon-button" aria-label="Import Python source" onClick={() => { if (canSwitch()) file.current?.click(); }}><Upload size={14}/></button><button className="icon-button" aria-label="Export Python source" disabled={!draft} onClick={() => draft && download(draft.name+'.py', draft.source, 'text/x-python')}><Download size={14}/></button><button className="icon-button" aria-label="Delete Python script" disabled={!draft || busy} onClick={async () => {
        if (!draft) return;
        setBusy(true); try { if (draft.revision) await api(`/scripts/${draft.id}`, { method: 'DELETE' }); setScripts(scripts.filter(s => s.id !== draft.id)); setDraft(null); setAnalysis(null); localStorage.removeItem(storageKey); } catch (e) { setError(String(e)); } finally { setBusy(false); }
      }}><Trash2 size={14}/></button><input hidden ref={file} type="file" accept=".py,text/x-python,text/plain" aria-label="Python source file" onChange={async e => {
        const selected = e.target.files?.[0]; if (!selected) return;
        try { if (selected.size > 500000) throw new Error('Source files must be smaller than 500 KB.'); newScript((await selected.text()).replace(/^\uFEFF/, ''), selected.name.replace(/\.py$/, '')); } catch (err) { setError(String(err)); }
        e.target.value = '';
      }}/>
    </div>
    {error && <p className="python-error" role="alert">{error}<button onClick={() => setError('')}>Dismiss</button></p>}
    {draft && <div className="python-metadata"><input aria-label="Python script name" maxLength={120} value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })}/><select aria-label="Python script type" value={draft.kind} onChange={e => setDraft({ ...draft, kind: e.target.value as StrategyDefinition['kind'] })}><option value="strategy">Strategy</option><option value="indicator">Indicator</option></select><span>{busy ? 'Saving…' : dirty ? 'Draft saved in this browser · save a version to keep history' : `Saved version ${draft.revision}`}</span><span className="toolbar-spacer"/><span>Import and save do not execute code</span></div>}
    {draft && <div className="python-keyboard"><label><input ref={tabModeControl} type="checkbox" checked={tabMovesFocus} onChange={e => setTabMovesFocus(e.target.checked)}/>Tab moves focus</label><span>{tabMovesFocus ? "Tab moves to the next control." : "Tab indents code."} Escape leaves the editor after closing suggestions.</span></div>}
    <div className="python-body">{draft ? <><div className="python-editor-host" onKeyDownCapture={event => {
      // Preserve native Tab navigation before Monaco's indentation bindings run.
      if (tabMovesFocus && event.key === 'Tab') event.stopPropagation();
    }}><Editor language="python" path={draft.id+'.py'} value={draft.source} theme={theme === 'dark' ? 'vs-dark' : 'light'} onMount={instance => {
      editor.current = instance;
      instance.addAction({ id: 'workbench.leave-python-editor', label: 'Leave Python editor', keybindings: [monaco.KeyCode.Escape],
        precondition: 'editorTextFocus && !suggestWidgetVisible && !findWidgetVisible && !inSnippetMode',
        run: () => tabModeControl.current?.focus() });
    }} onChange={value => setDraft(previous => previous ? { ...previous, source: value ?? '' } : previous)} options={{ automaticLayout: true, minimap: { enabled: false }, fontSize: 12, scrollBeyondLastLine: false, tabSize: 4, wordWrap: 'on', accessibilitySupport: 'on', ariaLabel: 'Python source editor. Escape returns to the Tab moves focus control.', tabFocusMode: tabMovesFocus }}/></div><aside className="python-diagnostics">{versions ? <><h4>Version history</h4>{versions.map(v => <button key={v.revision} onClick={() => { if (canSwitch()) { setDraft({ ...draft, source: v.source, kind: v.kind, name: v.name }); setVersions(null); } }}>Load version {v.revision}</button>)}<p>Loading a version creates a draft. Save it to record a new revision.</p></> : <><h4>{analysis ? analysis.valid ? 'Syntax and declarations valid' : 'Diagnostics' : 'Checking source…'}</h4>{analysis?.diagnostics.map((d, i) => <button className={d.severity} key={i} onClick={() => { editor.current?.revealLineInCenter(d.line); editor.current?.setPosition({ lineNumber: d.line, column: d.column }); editor.current?.focus(); }}>Line {d.line}: {d.message}</button>)}{analysis?.valid && <p>Static checks do not establish runtime correctness.</p>}{!!Object.keys(analysis?.parameters ?? {}).length && <><h4>Declared parameters</h4>{Object.entries(analysis!.parameters).map(([key, value]) => <p key={key}><b>{key}</b> · {value.type} · default {String(value.default)}<br/>{value.description}</p>)}</>}</>}</aside></> : <div className="panel-empty">Create a Python script or import a source file. Scripts stay local.</div>}</div>
    {runOpen && draft && analysis && <RunDialog script={draft} analysis={analysis} datasets={datasets} activeDataset={activeDataset} onClose={() => setRunOpen(false)} onRun={onRun} replay={replay}/>}
  </section>;
}
