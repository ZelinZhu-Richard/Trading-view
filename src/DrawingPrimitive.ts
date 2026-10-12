import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { ISeriesPrimitive, PrimitiveHoveredItem, SeriesAttachedParameter, Time, UTCTimestamp } from 'lightweight-charts';
import type { Anchor, Bar, Drawing } from './contracts';
import { drawingShapes, drawingTools, shapeHit, type DrawingKind, type Point, type Shape } from './drawingGeometry';

export class DrawingPrimitive implements ISeriesPrimitive<Time> {
  private context: SeriesAttachedParameter<Time> | null = null;
  private drawings: Drawing[] = [];
  private selected: string | null = null;
  private preview: Drawing | null = null;
  private riskLabels: Record<string, string> = {};
  private rendered: { drawing: Drawing; shapes: Shape[]; points: (Point | null)[] }[] = [];
  private views = [{ zOrder: () => 'top' as const, renderer: () => ({ draw: (target: CanvasRenderingTarget2D) => this.draw(target) }) }];
  constructor(private bars: Bar[], private instrumentId: string) {}
  attached(context: SeriesAttachedParameter<Time>) { this.context = context; }
  detached() { this.context = null; this.rendered = []; }
  paneViews() { return this.views; }
  update(drawings: Drawing[], selected: string | null, preview: Drawing | null = null) {
    this.drawings = drawings; this.selected = selected; this.preview = preview; this.context?.requestUpdate();
  }
  private index(time: number) {
    let low = 0, high = this.bars.length;
    while (low < high) { const mid = (low+high) >>> 1; if (this.bars[mid].start < time) low = mid+1; else high = mid; }
    return low;
  }
  project = (time: number, price: number): Point | null => {
    if (!this.context || !this.bars.length) return null;
    const scale = this.context.chart.timeScale();
    let x: number | null = scale.timeToCoordinate(time as UTCTimestamp);
    if (x == null) {
      const i = Math.max(1, Math.min(this.bars.length-1, this.index(time)));
      const a = this.bars[i-1] ?? this.bars[0], b = this.bars[i] ?? a;
      const ax = scale.timeToCoordinate(a.start as UTCTimestamp), bx = scale.timeToCoordinate(b.start as UTCTimestamp);
      if (ax != null && bx != null && b.start !== a.start) x = ax+(time-a.start)/(b.start-a.start)*(bx-ax);
    }
    const y = this.context.series.priceToCoordinate(price);
    return x != null && y != null && Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
  };
  anchor(point: Point, snap: boolean): Anchor | null {
    if (!this.context || !this.bars.length) return null;
    const scale = this.context.chart.timeScale();
    const width = scale.width(), height = this.context.chart.panes()[0].getHeight();
    if (point.x < 0 || point.x > width || point.y < 0 || point.y > height) return null;
    let price: number | null = this.context.series.coordinateToPrice(point.y);
    const exact = scale.coordinateToTime(point.x) as number | null;
    let time = exact;
    if (time == null) {
      const logical = scale.coordinateToLogical(point.x);
      if (logical == null) return null;
      const last = this.bars.at(-1)!, first = this.bars[0];
      const firstLogical = scale.coordinateToLogical(scale.timeToCoordinate(first.start as UTCTimestamp) ?? 0) ?? 0;
      const i = Math.round(logical-firstLogical);
      const near = this.bars[Math.max(0, Math.min(this.bars.length-1, i))];
      time = i < 0 ? first.start+i*(this.bars[1]?.start-first.start || first.end-first.start)
        : i >= this.bars.length ? last.start+(i-this.bars.length+1)*(last.end-last.start) : near.start;
    }
    if (price == null || price <= 0 || time == null) return null;
    if (snap) {
      const i = Math.max(0, Math.min(this.bars.length-1, this.index(time)));
      const bar = this.bars[i];
      time = bar.start;
      price = [bar.open, bar.high, bar.low, bar.close].sort((a, b) => Math.abs(a-price!)-Math.abs(b-price!))[0];
    }
    return { schema_version: 1, time, price };
  }
  setRiskLabels(labels: Record<string, string>) { this.riskLabels = labels; this.context?.requestUpdate(); }
  updateAllViews() {
    if (!this.context) return;
    const width = this.context.chart.timeScale().width(), height = this.context.chart.panes()[0].getHeight();
    const objects = this.preview ? [...this.drawings.filter(d => d.id !== this.preview!.id), this.preview] : this.drawings;
    this.rendered = objects.filter(d => d.visible && d.instrument_id === this.instrumentId).map(drawing => ({ drawing,
      shapes: drawingShapes(drawing, this.project, width, height, this.bars, this.riskLabels[drawing.id]),
      points: drawing.anchors.map(a => this.project(a.time, a.price)),
    }));
  }
  pick(x: number, y: number): { id: string; anchor: number | null; locked: boolean } | null {
    const point = { x, y };
    for (const item of [...this.rendered].reverse()) {
      if (item.drawing.id === this.selected) {
        const index = item.points.findIndex(p => p && Math.hypot(p.x-x, p.y-y) <= 8);
        if (index >= 0) return { id: item.drawing.id, anchor: index, locked: item.drawing.locked };
      }
      if (item.shapes.some(shape => shapeHit(shape, point, 6+item.drawing.width/2))) return { id: item.drawing.id, anchor: null, locked: item.drawing.locked };
    }
    return null;
  }
  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    const hit = this.pick(x, y);
    return hit ? { externalId: hit.id, zOrder: 'top', cursorStyle: hit.locked ? 'default' : hit.anchor == null ? 'move' : 'crosshair' } : null;
  }
  private draw(target: CanvasRenderingTarget2D) {
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      for (const { drawing, shapes, points } of this.rendered) {
        ctx.save(); ctx.globalAlpha = drawing.opacity; ctx.strokeStyle = drawing.color; ctx.fillStyle = drawing.color;
        ctx.lineWidth = drawing.width; ctx.font = '11px system-ui'; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
        for (const shape of shapes) {
          if (shape.kind === 'text') {
            ctx.fillStyle = shape.color ?? drawing.color;
            ctx.fillText(shape.text, shape.point.x, shape.point.y); continue;
          }
          ctx.beginPath();
          if (shape.kind === 'ellipse') ctx.ellipse((shape.a.x+shape.b.x)/2, (shape.a.y+shape.b.y)/2, Math.abs(shape.b.x-shape.a.x)/2, Math.abs(shape.b.y-shape.a.y)/2, 0, 0, Math.PI*2);
          else {
            shape.points.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y));
            if (shape.closed) ctx.closePath();
          }
          if (shape.fill) { ctx.fillStyle = shape.fill; ctx.fill(); }
          ctx.stroke();
        }
        if (drawing.id === this.selected || drawing.id === this.preview?.id) {
          ctx.globalAlpha = 1; ctx.fillStyle = drawing.locked ? '#91a0b2' : '#fff'; ctx.lineWidth = 1.5;
          for (const point of points) if (point) { ctx.beginPath(); ctx.arc(point.x, point.y, 4, 0, Math.PI*2); ctx.fill(); ctx.stroke(); }
        }
        ctx.restore();
      }
    });
  }
}

export interface DrawingInteractionState {
  mode: DrawingKind | null;
  snap: boolean;
  drawings: Drawing[];
  selected: string | null;
  onSelect: (id: string | null) => void;
  onCommit: (drawings: Drawing[]) => void;
  onFinish: () => void;
}

export function attachDrawingInteractions(host: HTMLElement, primitive: DrawingPrimitive, instrumentId: string, state: () => DrawingInteractionState) {
  let draft: Drawing | null = null;
  let drag: { original: Drawing; origin: Anchor; anchor: number | null } | null = null;
  let brush = false;
  const point = (event: PointerEvent): Point => { const box = host.getBoundingClientRect(); return { x: event.clientX-box.x, y: event.clientY-box.y }; };
  const preview = (drawing: Drawing | null) => primitive.update(state().drawings, state().selected, drawing);
  const stop = (event: Event) => { event.preventDefault(); event.stopImmediatePropagation(); };
  const commit = (drawing: Drawing) => {
    const current = state();
    current.onCommit([...current.drawings.filter(d => d.id !== drawing.id), drawing]);
    current.onSelect(drawing.id); current.onFinish(); draft = null; drag = null; brush = false;
  };
  const down = (event: PointerEvent) => {
    if (event.button !== 0) return;
    const current = state(), pos = point(event), anchor = primitive.anchor(pos, current.snap);
    if (!anchor) return;
    if (current.mode) {
      stop(event);
      if (draft?.kind !== current.mode) draft = null;
      if (!draft) draft = { schema_version: 1, id: crypto.randomUUID(), kind: current.mode, instrument_id: instrumentId,
        anchors: [], color: '#70b8f0', opacity: 1, width: 2, quantity: '1', label: current.mode === 'text' ? 'Text' : '',
        levels: current.mode === 'fib-extension' ? [0, .618, 1, 1.618, 2.618] : [0, .236, .382, .5, .618, .786, 1], visible: true, locked: false };
      draft.anchors.push(anchor);
      const needed = drawingTools.find(t => t.kind === current.mode)!.anchors;
      if (current.mode === 'brush') { brush = true; host.setPointerCapture(event.pointerId); }
      if (needed && draft.anchors.length >= needed) commit(draft);
      else preview(draft);
      return;
    }
    draft = null;
    const hit = primitive.pick(pos.x, pos.y);
    current.onSelect(hit?.id ?? null);
    if (hit) {
      stop(event);
      if (hit.locked) return;
      const original = current.drawings.find(d => d.id === hit.id);
      if (original) { drag = { original, origin: anchor, anchor: hit.anchor }; host.setPointerCapture(event.pointerId); }
    }
  };
  const move = (event: PointerEvent) => {
    const current = state(), pos = point(event), anchor = primitive.anchor(pos, current.snap);
    if (!anchor) return;
    if (drag) {
      stop(event);
      const timeDelta = anchor.time-drag.origin.time, priceDelta = anchor.price-drag.origin.price;
      const anchors = drag.original.anchors.map((a, i) => drag!.anchor === i ? anchor : drag!.anchor == null ? { ...a, time: a.time+timeDelta, price: Math.max(Number.MIN_VALUE, a.price+priceDelta) } : a);
      draft = { ...drag.original, anchors }; preview(draft);
    } else if (draft && current.mode) {
      if (brush) {
        const previous = primitive.project(draft.anchors.at(-1)!.time, draft.anchors.at(-1)!.price);
        if (previous && Math.hypot(pos.x-previous.x, pos.y-previous.y) > 3 && draft.anchors.length < 10000) draft.anchors.push(anchor);
        preview(draft);
      } else preview({ ...draft, anchors: [...draft.anchors, anchor] });
    }
  };
  const up = (event: PointerEvent) => {
    if ((drag || brush) && draft) {
      stop(event);
      if (brush && draft.anchors.length < 2) { draft = null; preview(null); state().onFinish(); }
      else commit(draft);
    }
    drag = null; brush = false;
    if (host.hasPointerCapture(event.pointerId)) host.releasePointerCapture(event.pointerId);
  };
  const cancel = () => { draft = null; drag = null; brush = false; preview(null); };
  const finishPath = (event: Event) => { if (draft?.kind === 'path' && draft.anchors.length >= 2) { stop(event); commit(draft); } };
  const key = (event: KeyboardEvent) => {
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLSelectElement) return;
    if (event.key === 'Escape') { cancel(); state().onFinish(); }
    if (event.key === 'Enter') finishPath(event);
  };
  host.addEventListener('pointerdown', down, true); host.addEventListener('pointermove', move, true);
  host.addEventListener('pointerup', up, true); host.addEventListener('pointercancel', cancel, true);
  host.addEventListener('dblclick', finishPath, true); window.addEventListener('keydown', key);
  return () => {
    host.removeEventListener('pointerdown', down, true); host.removeEventListener('pointermove', move, true);
    host.removeEventListener('pointerup', up, true); host.removeEventListener('pointercancel', cancel, true);
    host.removeEventListener('dblclick', finishPath, true); window.removeEventListener('keydown', key);
  };
}
