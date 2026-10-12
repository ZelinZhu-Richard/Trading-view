import type { Bar, Drawing } from './contracts';
export type DrawingKind = Drawing['kind'];

export type Point = { x: number; y: number };
export type Stroke = { kind: 'stroke'; points: Point[]; closed?: boolean; fill?: string; dashed?: boolean };
export type Shape = Stroke | { kind: 'ellipse'; a: Point; b: Point; fill?: string }
  | { kind: 'text'; point: Point; text: string; color?: string };
export type Projection = (time: number, price: number) => Point | null;

export const drawingTools: { kind: DrawingKind; name: string; anchors: number; instruction: string }[] = [
  { kind: 'trend', name: 'Trend line', anchors: 2, instruction: 'Choose two endpoints.' },
  { kind: 'ray', name: 'Ray', anchors: 2, instruction: 'Choose its origin, then direction.' },
  { kind: 'extended', name: 'Extended line', anchors: 2, instruction: 'Choose two points on the line.' },
  { kind: 'horizontal', name: 'Horizontal line', anchors: 1, instruction: 'Choose a price.' },
  { kind: 'horizontal-ray', name: 'Horizontal ray', anchors: 1, instruction: 'Choose a starting time and price.' },
  { kind: 'vertical', name: 'Vertical line', anchors: 1, instruction: 'Choose a time.' },
  { kind: 'cross', name: 'Cross line', anchors: 1, instruction: 'Choose a time and price.' },
  { kind: 'parallel-channel', name: 'Parallel channel', anchors: 3, instruction: 'Choose two baseline points, then the channel width.' },
  { kind: 'regression-channel', name: 'Regression channel', anchors: 2, instruction: 'Choose the first and last source bars. Bands show ±2 residual standard deviations.' },
  { kind: 'pitchfork', name: 'Pitchfork', anchors: 3, instruction: 'Choose the handle, then two outer points.' },
  { kind: 'fib-retracement', name: 'Fibonacci retracement', anchors: 2, instruction: 'Choose the start and end of the price move.' },
  { kind: 'fib-extension', name: 'Fibonacci extension', anchors: 3, instruction: 'Choose a price move, then the extension origin.' },
  { kind: 'rectangle', name: 'Rectangle', anchors: 2, instruction: 'Choose opposite corners.' },
  { kind: 'ellipse', name: 'Ellipse', anchors: 2, instruction: 'Choose opposite corners of the bounding box.' },
  { kind: 'triangle', name: 'Triangle', anchors: 3, instruction: 'Choose three vertices.' },
  { kind: 'brush', name: 'Brush', anchors: 0, instruction: 'Drag to draw; release to finish.' },
  { kind: 'path', name: 'Path', anchors: 0, instruction: 'Click vertices; press Enter or double-click to finish.' },
  { kind: 'arrow', name: 'Arrow', anchors: 2, instruction: 'Choose its tail, then its head.' },
  { kind: 'text', name: 'Text', anchors: 1, instruction: 'Choose the label location; edit its text in Objects.' },
  { kind: 'price-range', name: 'Price range', anchors: 2, instruction: 'Choose the starting and ending prices.' },
  { kind: 'date-range', name: 'Date range', anchors: 2, instruction: 'Choose the starting and ending times.' },
  { kind: 'date-price-range', name: 'Date and price range', anchors: 2, instruction: 'Choose two points to measure elapsed time and price change.' },
  { kind: 'long-position', name: 'Long position', anchors: 3, instruction: 'Choose entry, stop below entry, then target above entry.' },
  { kind: 'short-position', name: 'Short position', anchors: 3, instruction: 'Choose entry, stop above entry, then target below entry.' },
];

function segment(a: Point, b: Point, closed = false): Stroke { return { kind: 'stroke', points: [a, b], closed }; }
function rect(a: Point, b: Point, fill = '#70b8f022'): Stroke {
  return { kind: 'stroke', points: [a, { x: b.x, y: a.y }, b, { x: a.x, y: b.y }], closed: true, fill };
}

/** Clip the mathematical line to the price-pane viewport, including verticals. */
export function clippedLine(a: Point, b: Point, width: number, height: number, mode: 'segment' | 'ray' | 'line'): Stroke | null {
  const dx = b.x-a.x, dy = b.y-a.y;
  if (!dx && !dy) return segment(a, b);
  let lo = mode === 'line' ? -Infinity : 0, hi = mode === 'segment' ? 1 : Infinity;
  for (const [p, q] of [[-dx, a.x], [dx, width-a.x], [-dy, a.y], [dy, height-a.y]]) {
    if (!p) { if (q < 0) return null; continue; }
    const ratio = q/p;
    if (p < 0) lo = Math.max(lo, ratio); else hi = Math.min(hi, ratio);
  }
  if (lo > hi) return null;
  return segment({ x: a.x+lo*dx, y: a.y+lo*dy }, { x: a.x+hi*dx, y: a.y+hi*dy });
}

export function regression(bars: Bar[]) {
  if (bars.length < 2) return null;
  const center = (bars.length-1)/2, mean = bars.reduce((s, b) => s+b.close, 0)/bars.length;
  let numerator = 0, denominator = 0;
  bars.forEach((b, i) => { numerator += (i-center)*(b.close-mean); denominator += (i-center)**2; });
  const slope = numerator/denominator, intercept = mean-slope*center;
  const deviation = Math.sqrt(bars.reduce((s, b, i) => s+(b.close-intercept-slope*i)**2, 0)/bars.length);
  return { first: intercept, last: intercept+slope*(bars.length-1), deviation };
}

/** Geometry is derived fresh from persistent time/price anchors on every redraw. */
export function drawingShapes(drawing: Drawing, project: Projection, width: number, height: number, bars: Bar[], riskLabel?: string): Shape[] {
  const points = drawing.anchors.map(a => project(a.time, a.price));
  if (!points.length || points.some(p => !p)) return [];
  const validPoints = points as Point[];
  const a = validPoints[0], b = validPoints[1] ?? a, c = validPoints[2] ?? b;
  const shapes: Shape[] = [];
  const line = (p: Point, q: Point, mode: 'segment' | 'ray' | 'line' = 'segment') => {
    const shape = clippedLine(p, q, width, height, mode); if (shape) shapes.push(shape);
  };
  const text = (point: Point, value: string) => shapes.push({ kind: 'text', point, text: value });
  switch (drawing.kind) {
    case 'trend': case 'ray': case 'extended':
      line(a, b, drawing.kind === 'trend' ? 'segment' : drawing.kind === 'ray' ? 'ray' : 'line'); break;
    case 'horizontal': line({ x: 0, y: a.y }, { x: width, y: a.y }); break;
    case 'horizontal-ray': line(a, { x: width, y: a.y }); break;
    case 'vertical': line({ x: a.x, y: 0 }, { x: a.x, y: height }); break;
    case 'cross': line({ x: 0, y: a.y }, { x: width, y: a.y }); line({ x: a.x, y: 0 }, { x: a.x, y: height }); break;
    case 'parallel-channel': {
      const delta = c.y-(a.y+(b.y-a.y)*(c.x-a.x)/(b.x-a.x || 1));
      line(a, b); line({ x: a.x, y: a.y+delta }, { x: b.x, y: b.y+delta });
      shapes.push({ kind: 'stroke', points: [a, b, { x: b.x, y: b.y+delta }, { x: a.x, y: a.y+delta }], closed: true, fill: drawing.color+'18' });
      break;
    }
    case 'regression-channel': {
      const [start, end] = [drawing.anchors[0].time, drawing.anchors[1]?.time ?? drawing.anchors[0].time].sort((x, y) => x-y);
      const sample = bars.filter(v => v.start >= start && v.start <= end);
      const fit = regression(sample);
      if (fit) for (const deviation of [-2, 0, 2]) {
        const p = project(sample[0].start, fit.first+deviation*fit.deviation), q = project(sample.at(-1)!.start, fit.last+deviation*fit.deviation);
        if (p && q) line(p, q);
      }
      text(a, `${sample.length} bars · ±2σ`); break;
    }
    case 'pitchfork': {
      const mid = { x: (b.x+c.x)/2, y: (b.y+c.y)/2 }, delta = { x: mid.x-a.x, y: mid.y-a.y };
      line(a, mid, 'ray'); line(b, { x: b.x+delta.x, y: b.y+delta.y }, 'ray'); line(c, { x: c.x+delta.x, y: c.y+delta.y }, 'ray'); line(b, c); break;
    }
    case 'fib-retracement': case 'fib-extension': {
      line(a, b); if (drawing.kind === 'fib-extension') line(b, c);
      const first = drawing.anchors[0], second = drawing.anchors[1] ?? first, origin = drawing.kind === 'fib-extension' ? drawing.anchors[2] ?? second : first;
      const x1 = Math.min(a.x, b.x, c.x), x2 = Math.max(a.x, b.x, c.x, x1+80);
      for (const level of drawing.levels) {
        const price = origin.price+(second.price-first.price)*level;
        const p = project(origin.time, price);
        if (p) { line({ x: x1, y: p.y }, { x: x2, y: p.y }); text({ x: x2+4, y: p.y }, `${level} · ${price.toLocaleString('en-US', { maximumFractionDigits: 5 })}`); }
      }
      break;
    }
    case 'rectangle': shapes.push(rect(a, b, drawing.color+'20')); break;
    case 'ellipse': shapes.push({ kind: 'ellipse', a, b, fill: drawing.color+'20' }); break;
    case 'triangle': shapes.push({ kind: 'stroke', points: [a, b, c], closed: true, fill: drawing.color+'20' }); break;
    case 'brush': case 'path': shapes.push({ kind: 'stroke', points: points as Point[] }); break;
    case 'arrow': {
      line(a, b);
      const angle = Math.atan2(b.y-a.y, b.x-a.x), length = 12;
      line(b, { x: b.x-length*Math.cos(angle-.45), y: b.y-length*Math.sin(angle-.45) });
      line(b, { x: b.x-length*Math.cos(angle+.45), y: b.y-length*Math.sin(angle+.45) }); break;
    }
    case 'text': text(a, drawing.label || 'Text'); break;
    case 'price-range': case 'date-range': case 'date-price-range': {
      shapes.push(rect(a, b, drawing.color+'16'));
      const first = drawing.anchors[0], second = drawing.anchors[1] ?? first;
      const delta = second.price-first.price, elapsed = Math.abs(second.time-first.time);
      const price = `${delta >= 0 ? '+' : ''}${delta.toFixed(4)} (${(delta/first.price*100).toFixed(2)}%)`;
      const time = `${(elapsed/86400).toFixed(2)} days · ${bars.filter(v => v.start >= Math.min(first.time, second.time) && v.start <= Math.max(first.time, second.time)).length} bars`;
      text({ x: Math.min(a.x, b.x), y: Math.min(a.y, b.y)-8 }, drawing.kind === 'price-range' ? price : drawing.kind === 'date-range' ? time : `${price} · ${time}`); break;
    }
    case 'long-position': case 'short-position': {
      const right = Math.max(a.x+80, b.x, c.x);
      shapes.push(rect(a, { x: right, y: b.y }, '#ed798133'), rect(a, { x: right, y: c.y }, '#3bc3a533'));
      line(a, { x: right, y: a.y }); text({ x: a.x, y: Math.min(a.y, b.y, c.y)-8 }, riskLabel ?? 'Entry / stop / target'); break;
    }
  }
  if (drawing.label && drawing.kind !== 'text') text({ x: a.x+5, y: a.y-8 }, drawing.label);
  return shapes;
}

export function distanceToSegment(p: Point, a: Point, b: Point) {
  const length = (b.x-a.x)**2+(b.y-a.y)**2;
  const t = length ? Math.max(0, Math.min(1, ((p.x-a.x)*(b.x-a.x)+(p.y-a.y)*(b.y-a.y))/length)) : 0;
  return Math.hypot(p.x-a.x-t*(b.x-a.x), p.y-a.y-t*(b.y-a.y));
}

export function shapeHit(shape: Shape, point: Point, tolerance = 6): boolean {
  if (shape.kind === 'text') return point.x >= shape.point.x && point.x <= shape.point.x+Math.max(40, shape.text.length*6) && Math.abs(point.y-shape.point.y) <= 12;
  if (shape.kind === 'ellipse') {
    const rx = Math.abs(shape.b.x-shape.a.x)/2, ry = Math.abs(shape.b.y-shape.a.y)/2;
    if (!rx || !ry) return distanceToSegment(point, shape.a, shape.b) <= tolerance;
    const distance = Math.hypot((point.x-(shape.a.x+shape.b.x)/2)/rx, (point.y-(shape.a.y+shape.b.y)/2)/ry);
    return Math.abs(distance-1)*Math.min(rx, ry) <= tolerance;
  }
  const points = shape.closed ? [...shape.points, shape.points[0]] : shape.points;
  return points.slice(1).some((p, i) => distanceToSegment(point, points[i], p) <= tolerance);
}
