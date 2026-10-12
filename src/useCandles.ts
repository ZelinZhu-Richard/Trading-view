import { useEffect, useRef, useState } from 'react';
import type { CandleStatus } from './contracts';

export function useCandles(datasetIds: string[]) {
  const ids = useRef(datasetIds); ids.current = datasetIds;
  const [states, setStates] = useState<Record<string, CandleStatus>>({});
  const [connection, setConnection] = useState('off');
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const key = [...new Set(datasetIds)].sort().join('|');
  useEffect(() => {
    if (!key) { setConnection('off'); return; }
    let socket: WebSocket | null = null, timer: ReturnType<typeof setTimeout>, stopped = false, attempts = 0;
    function connect() {
      if (stopped) return;
      setConnection('connecting');
      socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/candles/events`);
      socket.onopen = () => { if (stopped) return; attempts = 0; setConnection('connected'); setError(''); socket?.send(JSON.stringify({ action: 'subscribe', dataset_ids: [...new Set(ids.current)] })); };
      socket.onmessage = event => {
        if (stopped) return;
        const message = JSON.parse(event.data);
        if (message.type === 'candles') { setStates(previous => ({ ...previous, ...message.states })); setError(message.error ?? ''); }
        if (message.type === 'error') setError(message.detail);
      };
      socket.onclose = () => {
        if (stopped) return;
        setConnection('disconnected');
        if (attempts < 5) timer = setTimeout(connect, Math.min(15000, 1000*2**attempts++));
      };
    }
    connect();
    return () => { stopped = true; clearTimeout(timer); if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ action: 'unsubscribe' })); socket?.close(); };
  }, [key, retry]);
  return { states, connection, error, reconnect: () => setRetry(value => value+1) };
}
