import { describe, expect, it } from 'vitest';
import type { Bar, Drawing } from './contracts';
import { clippedLine, distanceToSegment, drawingShapes, drawingTools, regression, shapeHit } from './drawingGeometry';

const bars: Bar[] = [10, 12, 14, 16].map((close, i) => ({ schema_version: 1, start: i*60, end: (i+1)*60,
  open: close, high: close+1, low: close-1, close, volume: 1, complete: true, source: 'fixture', feed: 'geometry', adjustment: 'raw' }));
const drawing: Drawing = { schema_version: 1, id: 'test', kind: 'trend', instrument_id: 'TEST',
  anchors: [{ schema_version: 1, time: 0, price: 10 }, { schema_version: 1, time: 180, price: 16 }, { schema_version: 1, time: 120, price: 12 }],
  color: '#70b8f0', opacity: 1, width: 2, label: '', levels: [0, .5, 1], visible: true, locked: false, quantity: '1' };
const project = (time: number, price: number) => ({ x: time+10, y: 200-price*5 });

describe('drawing geometry', () => {
  it('clips rays and infinite vertical/horizontal lines without moving the origin', () => {
    expect(clippedLine({ x: 20, y: 20 }, { x: 40, y: 40 }, 100, 100, 'ray')?.points).toEqual([{ x: 20, y: 20 }, { x: 100, y: 100 }]);
    expect(clippedLine({ x: 20, y: 20 }, { x: 20, y: 40 }, 100, 100, 'line')?.points).toEqual([{ x: 20, y: 0 }, { x: 20, y: 100 }]);
    expect(clippedLine({ x: -20, y: 20 }, { x: -10, y: 40 }, 100, 100, 'segment')).toBeNull();
  });
  it('fits source-close regression with population residual spread', () => {
    expect(regression(bars)).toEqual({ first: 10, last: 16, deviation: 0 });
    const fit = regression(bars.map((b, i) => ({ ...b, close: [9, 13, 15, 15][i] })))!;
    expect(fit.first).toBeCloseTo(10);
    expect(fit.last).toBeCloseTo(16);
    expect(fit.deviation).toBeCloseTo(1);
  });
  it('derives Fibonacci levels in price space even with nonlinear screen projection', () => {
    const shapes = drawingShapes({ ...drawing, kind: 'fib-retracement', anchors: drawing.anchors.slice(0, 2) },
      (time, price) => ({ x: time+10, y: Math.log(price)*50 }), 500, 300, bars);
    const label = shapes.find(s => s.kind === 'text' && s.text.startsWith('0.5'));
    expect(label?.kind === 'text' && label.point.y).toBeCloseTo(Math.log(13)*50);
  });
  it('hit-tests degenerate lines and ellipse boundaries', () => {
    expect(distanceToSegment({ x: 3, y: 4 }, { x: 0, y: 0 }, { x: 0, y: 0 })).toBe(5);
    expect(shapeHit({ kind: 'ellipse', a: { x: 0, y: 0 }, b: { x: 100, y: 50 } }, { x: 100, y: 25 })).toBe(true);
    expect(shapeHit({ kind: 'ellipse', a: { x: 0, y: 0 }, b: { x: 100, y: 50 } }, { x: 50, y: 25 })).toBe(false);
  });
  it.each(drawingTools)('produces finite $kind geometry from persistent anchors', tool => {
    const shapes = drawingShapes({ ...drawing, kind: tool.kind }, project, 500, 300, bars);
    expect(shapes.length).toBeGreaterThan(0);
    expect(JSON.stringify(shapes)).not.toContain('null');
    const shifted = drawingShapes({ ...drawing, kind: tool.kind }, (t, p) => ({ x: project(t, p).x+20, y: project(t, p).y+10 }), 500, 300, bars);
    expect(shifted).not.toEqual(shapes);
    expect(drawing.anchors[0]).toEqual({ schema_version: 1, time: 0, price: 10 });
  });
});
