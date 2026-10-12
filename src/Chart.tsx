import { useEffect, useRef, useState } from 'react';
import { createChart, CandlestickSeries, BarSeries, LineSeries, AreaSeries, BaselineSeries,
  HistogramSeries, ColorType, PriceScaleMode, CrosshairMode, type IChartApi,
  type ISeriesApi, type SeriesType, type Time, type UTCTimestamp, type IRange, type LineWidth } from 'lightweight-charts';
import type { Bar, ChartState, DatasetView, Drawing, IndicatorDefinition, IndicatorResponse } from './contracts';
import { api, formatPrice } from './api';
import { tickPrecision } from './data';
import { DrawingPrimitive, attachDrawingInteractions, type DrawingInteractionState } from './DrawingPrimitive';
import type { DrawingKind } from './drawingGeometry';

export interface ChartHandle {
  fit: () => void;
  image: () => string;
  range: (range: IRange<Time>) => void;
  crosshair: (time: Time | null) => void;
}
interface Props {
  rangeIdentity?: string;
  cutoff?: number | null;
  chart: ChartState;
  definitions: IndicatorDefinition[];
  drawingMode: DrawingKind | null;
  drawingSnap: boolean;
  selectedDrawing: string | null;
  onDrawingSelect: (id: string | null) => void;
  onDrawingsChange: (drawings: Drawing[]) => void;
  onDrawingFinish: () => void;
  theme: 'dark' | 'light';
  active: boolean;
  onActivate: () => void;
  onLoaded: (data: DatasetView) => void;
  onReady?: (cutoff: number | null, datasetId: string) => void;
  register: (handle: ChartHandle | null) => void;
  onRange: (value: IRange<Time>) => void;
  onCrosshair: (time: Time | null) => void;
}

const chartKinds = { candlestick: CandlestickSeries, 'heikin-ashi': CandlestickSeries,
  bar: BarSeries, line: LineSeries, area: AreaSeries, baseline: BaselineSeries };

function heikinAshi(bars: Bar[]): Bar[] {
  let open = (bars[0].open + bars[0].close) / 2;
  let close = (bars[0].open + bars[0].high + bars[0].low + bars[0].close) / 4;
  return bars.map((b, i) => {
    open = i ? (open + close) / 2 : open;
    close = (b.open + b.high + b.low + b.close) / 4;
    return { ...b, open, close, high: Math.max(b.high, open, close), low: Math.min(b.low, open, close) };
  });
}

export function Chart(props: Props) {
  const { chart, theme, active } = props;
  const host = useRef<HTMLDivElement>(null);
  const instance = useRef<IChartApi | null>(null);
  const drawingPrimitive = useRef<DrawingPrimitive | null>(null);
  const [riskLabels, setRiskLabels] = useState<Record<string, string>>({});
  const [loadedData, setLoadedData] = useState<{ value: DatasetView; cutoff: number | null } | null>(null);
  const data = loadedData?.cutoff === (props.cutoff ?? null) && loadedData.value.dataset.id === chart.dataset_id ? loadedData.value : null;
  const setData = (value: DatasetView | null) => setLoadedData(value ? { value, cutoff: props.cutoff ?? null } : null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadedReadout, setReadout] = useState<Bar | null>(null);
  const readout = data ? loadedReadout : null;
  const [loadedStudies, setLoadedStudies] = useState<{ value: IndicatorResponse; key: string } | null>(null);
  const [studyError, setStudyError] = useState('');
  const savedRange = useRef<{ datasetId: string; range: IRange<Time>; cutoff: number | null; lastTime: number } | null>(null);
  const handlers = useRef(props); handlers.current = props;
  const studyRequest = JSON.stringify(chart.indicators.map(({ id, definition_id, parameters }) => ({ id, definition_id, parameters })));
  const studyKey = JSON.stringify([chart.dataset_id, studyRequest, props.cutoff ?? null]);
  const studies = loadedStudies?.key === studyKey ? loadedStudies.value : null;
  const setStudies = (value: IndicatorResponse | null) => setLoadedStudies(value ? { value, key: studyKey } : null);
  const riskRequest = JSON.stringify(chart.drawings.filter(d => d.kind.endsWith('-position')));

  useEffect(() => {
    if (data && (!chart.indicators.length || studies || studyError)) handlers.current.onReady?.(props.cutoff ?? null, data.dataset.id);
  }, [data, studies, studyError, chart.indicators.length, props.cutoff]);

  useEffect(() => {
    if (!data) return;
    const controller = new AbortController();
    api<Record<string, { label: string }>>('/drawings/measure', { method: 'POST', signal: controller.signal,
      body: JSON.stringify({ instrument: data.dataset.instrument, drawings: JSON.parse(riskRequest) }) })
      .then(result => { if (!controller.signal.aborted) setRiskLabels(Object.fromEntries(Object.entries(result).map(([id, value]) => [id, value.label]))); })
      .catch(() => { if (!controller.signal.aborted) setRiskLabels({}); });
    return () => controller.abort();
  }, [data, riskRequest]);

  useEffect(() => { drawingPrimitive.current?.update(chart.drawings, props.selectedDrawing); }, [chart.drawings, props.selectedDrawing, props.drawingMode]);
  useEffect(() => { drawingPrimitive.current?.setRiskLabels(riskLabels); }, [riskLabels]);
  useEffect(() => {
    setData(null); setReadout(null); setError('');
    if (!chart.dataset_id) return;
    const controller = new AbortController(); setLoading(true);
    api<DatasetView>(`/datasets/${chart.dataset_id}${props.cutoff == null ? '' : `?cutoff=${props.cutoff}`}`, { signal: controller.signal })
      .then(value => { if (controller.signal.aborted) return; setData(value); setReadout(value.bars.at(-1) ?? null); handlers.current.onLoaded(value); })
      .catch(e => { if (!controller.signal.aborted) setError(String(e)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [chart.dataset_id, props.cutoff]);

  useEffect(() => {
    setStudies(null); setStudyError('');
    if (!chart.dataset_id || !JSON.parse(studyRequest).length) return;
    const controller = new AbortController();
    api<IndicatorResponse>('/indicators/calculate', { method: 'POST', signal: controller.signal,
      body: JSON.stringify({ dataset_id: chart.dataset_id, instances: JSON.parse(studyRequest), cutoff: props.cutoff ?? null }) })
      .then(result => { if (!controller.signal.aborted) setStudies(result); })
      .catch(e => { if (!controller.signal.aborted) setStudyError(String(e)); });
    return () => controller.abort();
  }, [chart.dataset_id, studyRequest, props.cutoff]);

  useEffect(() => {
    if (!host.current || !data?.bars.length) return;
    const dark = theme === 'dark';
    const api = createChart(host.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: dark ? '#111820' : '#fff' },
        textColor: dark ? '#91a0b2' : '#536174', fontFamily: "'SFMono-Regular', Consolas, monospace", fontSize: 11,
        attributionLogo: true },
      grid: { vertLines: { color: dark ? '#1c2530' : '#eff2f6' }, horzLines: { color: dark ? '#1c2530' : '#eff2f6' } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: dark ? '#293342' : '#dfe5ed', mode: {
        linear: PriceScaleMode.Normal, logarithmic: PriceScaleMode.Logarithmic, percentage: PriceScaleMode.Percentage,
      }[chart.scale] },
      timeScale: { borderColor: dark ? '#293342' : '#dfe5ed', timeVisible: !['1d', '1w', '1mo'].includes(data.dataset.interval), rightOffset: 5 },
      localization: { timeFormatter: (t: number) => new Intl.DateTimeFormat('en-US', {
        timeZone: chart.timezone, dateStyle: 'medium', timeStyle: 'short',
      }).format(new Date(t * 1000)) },
    });
    instance.current = api;
    const common = { priceFormat: { type: 'price' as const, minMove: Number(data.dataset.instrument.price_tick),
      precision: tickPrecision(data.dataset.instrument.price_tick) } };
    const series = api.addSeries(chartKinds[chart.kind] as typeof CandlestickSeries, {
      ...common,
      ...(chart.kind === 'candlestick' || chart.kind === 'heikin-ashi' ? {
        upColor: '#3bc3a5', downColor: '#ed7981', wickUpColor: '#3bc3a5', wickDownColor: '#ed7981', borderVisible: false,
      } : {}),
    }) as ISeriesApi<SeriesType>;
    const bars = chart.kind === 'heikin-ashi' ? heikinAshi(data.bars) : data.bars;
    const ohlc = ['candlestick', 'bar', 'heikin-ashi'].includes(chart.kind);
    series.setData(bars.map(b => ({ time: b.start as UTCTimestamp,
      ...(ohlc ? { open: b.open, high: b.high, low: b.low, close: b.close } : { value: b.close }),
    })));
    const primitive = new DrawingPrimitive(data.bars, data.dataset.instrument.id);
    drawingPrimitive.current = primitive;
    series.attachPrimitive(primitive);
    primitive.update(chart.drawings, handlers.current.selectedDrawing);
    primitive.setRiskLabels(riskLabels);
    const drawingState = (): DrawingInteractionState => ({
      mode: handlers.current.drawingMode, snap: handlers.current.drawingSnap,
      drawings: handlers.current.chart.drawings, selected: handlers.current.selectedDrawing,
      onSelect: id => { handlers.current.onActivate(); handlers.current.onDrawingSelect(id); },
      onCommit: values => handlers.current.onDrawingsChange(values), onFinish: () => handlers.current.onDrawingFinish(),
    });
    const detachDrawingInteractions = attachDrawingInteractions(host.current, primitive, data.dataset.instrument.id, drawingState);
    if (chart.show_volume && data.bars.some(b => b.volume != null)) {
      const volume = api.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceLineVisible: false, lastValueVisible: false }, 1);
      volume.setData(data.bars.filter(b => b.volume != null).map(b => ({ time: b.start as UTCTimestamp,
        value: b.volume!, color: b.close >= b.open ? '#3bc3a555' : '#ed798155' })));
      api.panes()[0].setStretchFactor(4);
      api.panes()[1].setStretchFactor(1);
    }
    const occupied = chart.show_volume && data.bars.some(b => b.volume != null) ? [0, 1] : [0];
    const paneMap = new Map(occupied.map(i => [i, i]));
    const palette = ['#70b8f0', '#e9be72', '#ac91e7', '#6dcdb8', '#df91aa', '#aab7c9', '#ccbd8a'];
    if (studies?.dataset_id === data.dataset.id) {
      for (const study of studies.results) {
        const settings = chart.indicators.find(i => i.id === study.instance_id);
        if (!settings?.visible || study.status !== 'ready') continue;
        if (!paneMap.has(settings.pane)) paneMap.set(settings.pane, paneMap.size);
        const paneIndex = paneMap.get(settings.pane)!;
        study.lines.forEach((line, index) => {
          if (line.output_id === 'direction') return; // A sign is metadata, not a price-scale series.
          const histogram = line.output_id === 'histogram' || line.output_id === 'volume';
          const color = index === 0 ? settings.color : palette[index % palette.length];
          const lineSeries = api.addSeries(histogram ? HistogramSeries : LineSeries, {
            color, priceLineVisible: false, lastValueVisible: false,
            priceFormat: { type: line.output_id === 'volume' ? 'volume' : 'price', precision: 4, minMove: .0001 },
            ...(histogram ? {} : { lineWidth: settings.width as LineWidth,
              lineVisible: settings.definition_id !== 'parabolic_sar', pointMarkersVisible: settings.definition_id === 'parabolic_sar',
              pointMarkersRadius: 2 }),
          }, paneIndex);
          lineSeries.setData(line.values.flatMap((value, i) => {
            const time = line.plot_times[i] ?? (line.plot_offset_bars === 0 ? studies.times[i] : null);
            if (time == null) return [];
            if (value == null) return [{ time: time as UTCTimestamp }];
            const previous = line.values[i-1];
            const positive = settings.definition_id === 'awesome_oscillator' && previous != null ? value > previous : value >= 0;
            return [{ time: time as UTCTimestamp, value, ...(histogram ? { color: positive ? '#3bc3a5' : '#ed7981' } : {}) }];
          }));
          if (paneIndex) api.panes()[paneIndex].setStretchFactor(1);
        });
      }
      api.panes()[0].setStretchFactor(4);
    }
    const byTime = new Map(data.bars.map(b => [b.start, b]));
    let suppress = false;
    api.subscribeCrosshairMove(param => {
      if (suppress) return;
      const bar = byTime.get(param.time as number);
      setReadout(bar ?? data.bars.at(-1) ?? null);
      handlers.current.onCrosshair(param.time ?? null);
    });
    api.timeScale().subscribeVisibleTimeRangeChange(range => {
      if (!suppress && range) handlers.current.onRange(range);
    });
    handlers.current.register({
      fit: () => api.timeScale().fitContent(),
      image: () => api.takeScreenshot().toDataURL('image/png'),
      range: range => {
        const previous = api.timeScale().getVisibleRange();
        if (JSON.stringify(previous) === JSON.stringify(range)) return;
        suppress = true;
        try { api.timeScale().setVisibleRange(range); } finally { suppress = false; }
      },
      crosshair: time => {
        suppress = true;
        const b = byTime.get(time as number);
        if (time != null && b) { api.setCrosshairPosition(b.close, time, series); setReadout(b); }
        else { api.clearCrosshairPosition(); setReadout(data.bars.at(-1) ?? null); }
        suppress = false;
      },
    });
    const prior = savedRange.current;
    if (prior?.datasetId === (props.rangeIdentity ?? data.dataset.id) && (prior.cutoff === (props.cutoff ?? null) || (prior.cutoff != null && props.cutoff != null && props.cutoff >= prior.cutoff))) {
      const range = prior.range;
      if ((props.cutoff != null || props.rangeIdentity != null) && typeof range.from === 'number' && typeof range.to === 'number' && range.to >= prior.lastTime) {
        const shift = data.bars.at(-1)!.start-prior.lastTime;
        api.timeScale().setVisibleRange({ from: (range.from+shift) as Time, to: (range.to+shift) as Time });
      } else api.timeScale().setVisibleRange(range);
    } else api.timeScale().fitContent();
    return () => {
      const range = api.timeScale().getVisibleRange();
      if (range) savedRange.current = { datasetId: props.rangeIdentity ?? data.dataset.id, range, cutoff: props.cutoff ?? null, lastTime: data.bars.at(-1)!.start };
      detachDrawingInteractions(); drawingPrimitive.current = null;
      handlers.current.register(null); instance.current = null; api.remove();
    };
  }, [data, chart.kind, chart.scale, chart.timezone, chart.show_volume, chart.indicators, studies, theme]);

  return <section className={`chart-tile ${active ? 'active' : ''}`} onPointerDown={props.onActivate} onFocus={props.onActivate} tabIndex={0}
    aria-label={`Chart ${chart.id}`} aria-description="Arrow keys pan. Plus and minus zoom. Home fits all data. Source values are available in the Data table."
    onKeyDown={event => {
      if (event.target !== event.currentTarget || !instance.current) return;
      const scale = instance.current.timeScale();
      if (event.key === 'Home') { event.preventDefault(); scale.fitContent(); }
      else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault(); scale.scrollToPosition(scale.scrollPosition() + (event.key === 'ArrowLeft' ? -10 : 10), false);
      } else if (['+', '=', '-'].includes(event.key)) {
        const range = scale.getVisibleLogicalRange();
        if (!range) return;
        event.preventDefault();
        const center = (range.from + range.to)/2, half = Math.max(1, (range.to-range.from)/2 * (event.key === '-' ? 1.2 : .8));
        scale.setVisibleLogicalRange({ from: center-half, to: center+half });
      }
    }}>
    <div className="chart-heading"><span className="instrument-dot"/><strong>{data?.dataset.instrument.symbol ?? 'Select an instrument'}</strong>
      <span>{data?.dataset.interval.toUpperCase()} {data && '· ' + data.dataset.instrument.exchange}</span>
      <span className="chart-source">{data?.dataset.source === 'fixture' ? 'SYNTHETIC EXAMPLE' : data?.dataset.source.toUpperCase()}</span>
    </div>
    {readout && <div className="ohlc">{(['open', 'high', 'low', 'close'] as const).map(key => <span key={key}>{key[0].toUpperCase()} <b>{formatPrice(readout[key])}</b></span>)}<span>V <b>{readout.volume?.toLocaleString() ?? 'Unavailable'}</b></span></div>}
    {!!chart.indicators.length && <div className="study-readouts" aria-label="Indicator values">{chart.indicators.filter(i => i.visible).map(settings => {
      const result = studies?.results.find(r => r.instance_id === settings.id);
      const index = studies?.times.indexOf(readout?.start ?? 0) ?? -1;
      const name = props.definitions.find(d => d.id === settings.definition_id)?.name ?? settings.definition_id;
      return <span key={settings.id} style={{ borderLeftColor: settings.color }} title={result?.message ?? studyError}>
        <b>{name}</b> {result?.status === 'ready' ? result.lines.filter(l => l.output_id !== 'direction').map(line => `${line.output_id}: ${line.values[index] == null ? '—' : formatPrice(line.values[index]!)}`).join(' · ') : result?.message ?? (studyError || 'Calculating…')}
      </span>;
    })}</div>}
    <div className="chart-canvas" ref={host} style={{ visibility: data?.bars.length ? 'visible' : 'hidden' }}/>{data && !data.bars.length && <div className="chart-empty"><p>No completed bars at this replay cursor.</p></div>}
    {!data && <div className="chart-empty">{loading ? <p>Loading dataset…</p> : error ? <p role="alert">{error}</p> : <><span className="empty-symbol">↗</span><h2>Your next idea starts here</h2><p>Import market data or open the synthetic example.</p></>}</div>}
    {chart.kind === 'heikin-ashi' && data && <div className="chart-note">Heikin-Ashi display · source OHLC retained for calculations</div>}
  </section>;
}
