import type { ChartState, Dataset, Workspace } from './contracts';

const seconds: Record<string, number> = { '1m': 60, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '4h': 14400, '1d': 86400 };
export function canAggregate(source: string, target: string) {
  if (source === target) return true;
  if (!seconds[source]) return false;
  if (target === '1w' || target === '1mo') return true;
  return !!seconds[target] && seconds[target] > seconds[source] && seconds[target] % seconds[source] === 0;
}

export function intervalSource(selected: Dataset | undefined, datasets: Dataset[], interval: string): Dataset | undefined {
  let candidate = selected;
  const visited = new Set<string>();
  while (candidate && !visited.has(candidate.id)) {
    visited.add(candidate.id);
    if (canAggregate(candidate.interval, interval)) return candidate;
    candidate = datasets.find(d => d.id === candidate?.parent_id);
  }
  return undefined;
}

export function tickPrecision(tick: string) {
  const [coefficient, exponent = '0'] = Number(tick).toString().split('e');
  return Math.max(0, (coefficient.split('.')[1]?.length ?? 0) - Number(exponent));
}

export function sharesGroup(a: ChartState, b: ChartState) {
  return a.link_group != null && a.link_group === b.link_group;
}

export function linkedCharts(workspace: Workspace, active: ChartState, kind: 'symbol' | 'interval' | 'crosshair' | 'range') {
  return workspace.charts.slice(0, workspace.layout).filter(chart => chart.id === active.id || (workspace[`link_${kind}`] && sharesGroup(chart, active)));
}
