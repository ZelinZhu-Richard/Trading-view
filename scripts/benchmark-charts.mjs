import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import os from 'node:os';
const endpoint = 'http://127.0.0.1:8000/api';
const headers = { 'X-Workbench-Request': '1', 'Content-Type': 'application/json' };
const request = async (path, data, method = 'POST') => {
  const response = await fetch(endpoint + path, data ? { method, headers, body: JSON.stringify(data) } : {});
  const result = await response.json();
  if (!response.ok) throw new Error(JSON.stringify(result));
  return result;
};
await mkdir('evidence/performance', { recursive: true });
const original = await request('/workspaces/default');
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
page.setDefaultTimeout(60000);
const errors = [], calculations = [];
page.on('pageerror', error => errors.push(error.message));
page.on('response', async response => {
  if (response.url().endsWith('/api/indicators/calculate')) {
    await response.finished();
    const time = response.request().timing();
    calculations.push({ status: response.status(), request_ms: time.responseEnd });
  }
});
let dataset;
try {
  const start = Date.UTC(2025, 0, 1);
  const rows = Array.from({ length: 10000 }, (_, i) => {
    const close = 100 + i*.002 + Math.sin(i*.07)*3;
    return `${new Date(start+i*60000).toISOString()},${close},${close+1},${close-1},${close},${100+i%27}`;
  });
  const preview = await request('/imports/preview', {
    csv_text: 'timestamp,open,high,low,close,volume\n'+rows.join('\n'), timezone: 'UTC', interval: '1m',
    instrument: { id: 'EXAMPLE:PERFORMANCE', symbol: 'PERFORMANCE', name: 'Synthetic chart workload, not market data',
      exchange: 'EXAMPLE', asset_class: 'other', quote_currency: 'USD', timezone: 'UTC', calendar: '24/7' },
  });
  if (!preview.can_commit) throw new Error(JSON.stringify(preview.errors));
  dataset = await request('/imports/commit', { token: preview.token });
  const ids = ['ema', 'sma', 'rsi', 'macd', 'bollinger_bands'];
  const current = await request('/workspaces/default');
  await request('/workspaces/default', { ...current, theme: 'dark', layout: 4, active_chart: 0, bottom_open: false,
    charts: current.charts.map((chart, i) => ({ ...chart, dataset_id: dataset.id,
      indicators: ids.map((id, k) => ({ id: `bench-${i}-${id}`, definition_id: id, parameters: {},
        color: '#70b8f0', width: 2, pane: id === 'rsi' ? 2 : id === 'macd' ? 3 : 0, visible: true })) })) }, 'PUT');
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Performance.enable');
  const started = performance.now();
  await page.goto('http://127.0.0.1:5173/');
  await expect(page.locator('.study-readouts')).toHaveCount(4);
  for (let i = 0; i < 4; i++) {
    await expect(page.locator('.study-readouts').nth(i)).not.toContainText('Calculating');
    await expect(page.locator('.study-readouts').nth(i)).toContainText('Relative strength index');
  }
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const readyMs = performance.now() - started;
  const before = await cdp.send('Performance.getMetrics');
  const box = await page.locator('.chart-canvas').first().boundingBox();
  const interactions = [];
  for (let i = 0; i < 6; i++) {
    const t = performance.now();
    await page.mouse.move(box.x+box.width*.6, box.y+box.height*.3);
    await page.mouse.down();
    await page.mouse.move(box.x+box.width*.35, box.y+box.height*.3, { steps: 5 });
    await page.mouse.up();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    interactions.push(performance.now()-t);
  }
  await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
  const after = await cdp.send('Performance.getMetrics');
  const metric = (data, name) => data.metrics.find(m => m.name === name)?.value;
  await page.screenshot({ path: 'evidence/performance/four-charts.png' });
  if (errors.length) throw new Error(errors.join('\n'));
  const report = { date: new Date().toISOString(), status: 'passed', browser: await browser.version(),
    hardware: { platform: os.platform(), release: os.release(), arch: os.arch(), logical_cpus: os.cpus().length, cpu_model: os.cpus()[0]?.model, physical_memory_bytes: os.totalmem() },
    workload: { charts: 4, bars_per_chart: 10000, indicators_per_chart: 5, indicators: ids, dataset_id: dataset.id,
      source: 'explicitly synthetic CSV, same immutable dataset in all four charts', viewport: [1920, 1080] },
    measurements: { navigation_to_four_ready_charts_ms: readyMs, calculation_requests: calculations,
      six_five_step_drag_and_two_frame_roundtrip_ms: interactions,
      renderer_js_heap_before_bytes: metric(before, 'JSHeapUsedSize'), renderer_js_heap_after_bytes: metric(after, 'JSHeapUsedSize'),
      renderer_task_duration_delta_seconds: metric(after, 'TaskDuration')-metric(before, 'TaskDuration') },
    limitations: ['One macOS Chrome run, development build; timings include automation overhead.',
      'Renderer JS heap is not whole-process RSS; no total application peak-memory claim.',
      'Concurrent research jobs, other browsers/platforms and cold provider-network workloads remain unverified.'], pageErrors: errors };
  await writeFile('evidence/performance/charts.json', JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
} finally {
  await page.close();
  const latest = await request('/workspaces/default');
  await request('/workspaces/default', { ...original, revision: latest.revision }, 'PUT');
  await browser.close();
}
