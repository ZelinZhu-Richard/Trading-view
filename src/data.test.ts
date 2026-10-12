import { describe, expect, it } from 'vitest';
import { canAggregate, tickPrecision } from './data';

describe('interval capabilities and price increments', () => {
  it('does not imply unavailable finer or incompatible data', () => {
    expect(canAggregate('1d', '1h')).toBe(false);
    expect(canAggregate('1w', '1mo')).toBe(false);
    expect(canAggregate('1d', '1w')).toBe(true);
    expect(canAggregate('15m', '4h')).toBe(true);
  });
  it('retains fractional tick digits rather than rounding non-power-of-ten ticks', () => {
    expect(tickPrecision('0.25')).toBe(2);
    expect(tickPrecision('0.000010')).toBe(5);
    expect(tickPrecision('1E-8')).toBe(8);
    expect(tickPrecision('5')).toBe(0);
  });
});

import type { ChartState, Workspace } from './contracts';
import { linkedCharts, sharesGroup } from './data';

it('links only visible charts in the active nonempty group', () => {
  const charts = ['main', 'main', 'second', null].map((link_group, index) => ({ id: `chart-${index}`, link_group })) as ChartState[];
  const workspace = { charts, layout: 4, link_symbol: true, link_interval: false } as Workspace;
  expect(linkedCharts(workspace, charts[0], 'symbol').map(c => c.id)).toEqual(['chart-0', 'chart-1']);
  expect(linkedCharts(workspace, charts[0], 'interval').map(c => c.id)).toEqual(['chart-0']);
  expect(linkedCharts({ ...workspace, layout: 1 }, charts[0], 'symbol')).toEqual([charts[0]]);
  expect(linkedCharts(workspace, charts[3], 'symbol')).toEqual([charts[3]]);
  expect(sharesGroup(charts[3], { ...charts[2], link_group: null })).toBe(false);
});
