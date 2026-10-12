import { useEffect, useRef, useState } from 'react';
import type { Instrument, Quote } from './contracts';

export function useQuotes(instruments: Instrument[]) {
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [status, setStatus] = useState('connecting');
  const [clock, setClock] = useState(Date.now());
  const instrumentsRef = useRef(instruments); instrumentsRef.current = instruments;
  const identity = instruments.map(i => i.id).sort().join('|');
  useEffect(() => {
    let socket: WebSocket | null = null, timer: ReturnType<typeof setTimeout>, stopped = false, attempts = 0;
    const connect = () => {
      if (stopped) return;
      socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/events`);
      socket.onopen = () => {
        attempts = 0; setStatus('connected');
        socket?.send(JSON.stringify({ action: 'subscribe', subscription: 'health' }));
        for (const instrument of instrumentsRef.current) {
          const provider = ['coinbase', 'alpaca'].find(p => instrument.provider_symbols[p]);
          if (provider) socket?.send(JSON.stringify({ action: 'subscribe', subscription: `quote:${instrument.id}`, provider, instrument }));
        }
      };
      socket.onmessage = event => {
        const message = JSON.parse(event.data);
        if (message.type === 'quote') setQuotes(previous => ({ ...previous, [message.quote.instrument_id]: message.quote }));
        if (message.type === 'status' && message.status !== 'connected') {
          const id = String(message.subscription).replace(/^quote:/, '');
          setQuotes(previous => previous[id] ? { ...previous, [id]: { ...previous[id], freshness: 'stale' } } : previous);
        }
      };
      socket.onclose = () => {
        if (stopped) return;
        setStatus('disconnected');
        setQuotes(previous => Object.fromEntries(Object.entries(previous).map(([k, v]) => [k, { ...v, freshness: 'stale' }])));
        if (!stopped && attempts < 5) timer = setTimeout(connect, Math.min(15000, 1000 * 2 ** attempts++));
      };
    };
    connect();
    return () => { stopped = true; clearTimeout(timer); socket?.close(); };
  }, [identity]);
  useEffect(() => { const timer = setInterval(() => setClock(Date.now()), 5000); return () => clearInterval(timer); }, []);
  const fresh = Object.fromEntries(Object.entries(quotes).map(([key, quote]) => [key,
    clock / 1000 - quote.timestamp > 90 ? { ...quote, freshness: 'stale' as const } : quote]));
  return { quotes: fresh, connectionStatus: status };
}
