import { useCallback, useEffect, useRef, useState } from 'react';
import type { Workspace } from './contracts';
import { api } from './api';

export function useWorkspace() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [saveStatus, setSaveStatus] = useState('Loading workspace…');
  const [saveError, setSaveError] = useState('');
  const draft = useRef<Workspace | null>(null);
  const revision = useRef(0);
  const saved = useRef('');
  const saving = useRef(false);
  const blocked = useRef(false);
  const mounted = useRef(true);

  const load = useCallback(async () => {
    try {
      const value = await api<Workspace>('/workspaces/default');
      revision.current = value.revision;
      draft.current = value; saved.current = JSON.stringify(value);
      blocked.current = false; setWorkspace(value); setSaveError(''); setSaveStatus('Saved locally');
    } catch (e) { setSaveError(String(e)); setSaveStatus('Service unavailable'); }
  }, []);
  useEffect(() => { mounted.current = true; void load(); return () => { mounted.current = false; }; }, [load]);

  const save = useCallback(async () => {
    if (saving.current || blocked.current || !draft.current) return;
    saving.current = true;
    try {
      while (draft.current && JSON.stringify(draft.current) !== saved.current) {
        const next = draft.current;
        const encoded = JSON.stringify(next);
        setSaveStatus('Saving…');
        const value = await api<Workspace>('/workspaces/default', {
          method: 'PUT', body: JSON.stringify({ ...next, revision: revision.current }),
        });
        revision.current = value.revision;
        saved.current = encoded;
      }
      if (mounted.current) { setSaveStatus('Saved locally'); setSaveError(''); }
    } catch (e) {
      blocked.current = true;
      if (mounted.current) { setSaveError(String(e)); setSaveStatus('Not saved'); }
    } finally { saving.current = false; }
  }, []);

  useEffect(() => {
    draft.current = workspace;
    if (!workspace || JSON.stringify(workspace) === saved.current) return;
    setSaveStatus('Unsaved changes');
    const timer = setTimeout(() => { void save(); }, 500);
    return () => clearTimeout(timer);
  }, [workspace, save]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (draft.current && JSON.stringify(draft.current) !== saved.current) {
        event.preventDefault(); event.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, []);

  const retry = () => { blocked.current = false; void save(); };
  return { workspace, setWorkspace, saveStatus, saveError, reloadWorkspace: load, retrySave: retry };
}
