import { browserExecutable, evidenceDirectory } from './browser-runtime.mjs';
import { chromium, expect } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
import os from 'node:os';
const browser = await chromium.launch({ executablePath: browserExecutable, headless: true });
const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
const page = await context.newPage(); page.setDefaultTimeout(15000);
const base = 'http://127.0.0.1:8000/api', headers = { 'X-Workbench-Request': '1' };
async function call(path, data, method='POST') {
  const r = data ? await context.request.fetch(base+path, { method, headers, data }) : await context.request.get(base+path);
  if (!r.ok()) throw new Error(await r.text()); return r.json();
}
const original = await call('/workspaces/default'), errors = [], timings = [];
page.on('pageerror', e => errors.push(e.message));
const stamp = Date.now();
async function fixture(symbol) {
  const preview = await call('/imports/preview', { interval: '1d', timezone: 'UTC', instrument: { id: `EXAMPLE:${symbol}-${stamp}`, symbol, name: 'Synthetic linking fixture', exchange: 'EXAMPLE', asset_class: 'other', quote_currency: 'USD', timezone: 'UTC', calendar: '24/7' }, csv_text: 'timestamp,open,high,low,close,volume\n'+Array.from({ length: 140 }, (_, i) => `${new Date(Date.UTC(2025,0,1+i)).toISOString()},${100+i},${102+i},${99+i},${101+i},10`).join('\n') });
  if (!preview.can_commit) throw new Error(JSON.stringify(preview.errors)); return call('/imports/commit', { token: preview.token });
}
async function choose(symbol, interval='1d') {
  await page.locator('.symbol-picker').click();
  await page.getByLabel('Search datasets').fill(symbol);
  await page.locator('.dataset-picker button').filter({ hasText: new RegExp(`${interval}\\s+csv`) }).first().click();
  await expect(page.locator('.symbol-picker')).toContainText(symbol);
  await expect(page.getByLabel('Chart interval', { exact: true })).toHaveValue(interval);
  await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
}
try {
  const a = await fixture('LINKA'), b = await fixture('LINKB');
  const weekly = await call(`/datasets/${a.id}/aggregate?interval=1w`, {});
  await call('/workspaces/default', { ...original, layout: 4, active_chart: 0, link_symbol: true, link_interval: false, link_range: false, charts: original.charts.map((c, i) => ({ ...c, dataset_id: i === 1 ? weekly.id : a.id, follow_live: false, link_group: i < 2 ? 'main' : i === 2 ? 'second' : null, drawings: [], indicators: [] })) }, 'PUT');
  await page.goto('http://127.0.0.1:5173/');
  await choose('LINKB');
  let ws = await call('/workspaces/default'), datasets = await call('/datasets');
  const meta = id => datasets.find(d => d.id === id);
  if (meta(ws.charts[0].dataset_id).id !== b.id || meta(ws.charts[1].dataset_id).instrument.id !== b.instrument.id || meta(ws.charts[1].dataset_id).interval !== '1w' || ws.charts[2].dataset_id !== a.id || ws.charts[3].dataset_id !== a.id) throw new Error('Selective symbol linking or independent interval failed');
  await page.getByRole('button', { name: 'Chart linking settings' }).click();
  await page.getByLabel('Active chart link group').selectOption('');
  await page.getByRole('button', { name: 'Chart linking settings' }).click();
  await choose('LINKA');
  ws = await call('/workspaces/default');
  if (meta(ws.charts[1].dataset_id).instrument.id !== b.instrument.id) throw new Error('Independent chart changed another group');
  await page.getByRole('button', { name: 'Chart linking settings' }).click();
  await page.getByLabel('Active chart link group').selectOption('main');
  await page.locator('.link-popover').getByLabel('interval', { exact: true }).check();
  await page.getByRole('button', { name: 'Chart linking settings' }).click();
  await page.getByLabel('Chart interval', { exact: true }).selectOption('1w');
  await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
  ws = await call('/workspaces/default'); datasets = await call('/datasets');
  if (meta(ws.charts[0].dataset_id).interval !== '1w' || meta(ws.charts[1].dataset_id).interval !== '1w' || meta(ws.charts[1].dataset_id).instrument.id !== b.instrument.id) throw new Error('Interval linking changed symbol or ignored group');
  for (const kind of ['candlestick', 'bar', 'line', 'area', 'baseline', 'heikin-ashi']) {
    await page.getByLabel('Chart type', { exact: true }).selectOption(kind);
    await expect(page.locator('.chart-tile').first().locator('canvas').first()).toBeVisible();
  }
  for (const scale of ['linear', 'logarithmic', 'percentage']) await page.getByLabel('Price scale', { exact: true }).selectOption(scale);
  await page.getByLabel('Price scale', { exact: true }).selectOption('linear');
  const session = await context.newCDPSession(page); await session.send('Performance.enable');
  for (let i=0; i<8; i++) {
    const begin = performance.now(); await choose(i%2 ? 'LINKA' : 'LINKB');
    await page.getByLabel('Chart interval', { exact: true }).selectOption('1w');
    await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
    timings.push(performance.now()-begin);
  }
  const metrics = await session.send('Performance.getMetrics');
  await page.getByRole('button', { name: 'Chart linking settings' }).focus(); await page.keyboard.press('Tab');
  const focus = await page.evaluate(() => ({ tag: document.activeElement?.tagName, outline: getComputedStyle(document.activeElement).outlineWidth }));
  if (focus.tag === 'BODY' || focus.outline === '0px') throw new Error('Keyboard focus indicator missing');
  await page.screenshot({ path: `${evidenceDirectory}/links-1920.png` });
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.screenshot({ path: `${evidenceDirectory}/links-1280.png` });
  if (errors.length) throw new Error(errors.join('\n'));
  const report = { passed: true, browser: await browser.version(), checks: ['symbol linking restricted to visible matching nonempty group', 'unlinked intervals preserved', 'independent group stays independent', 'interval linking preserves other symbols', 'six chart variants and three scales render', 'keyboard focus visible'], loops: timings.length, roundtripMs: timings, automationOverheadIncluded: true, rendererHeapBytes: metrics.metrics.find(m => m.name === 'JSHeapUsedSize')?.value, hardware: { arch: os.arch(), cpus: os.cpus().length, memory: os.totalmem() }, errors };
  await writeFile(`${evidenceDirectory}/links-report.json`, JSON.stringify(report,null,2)); console.log(JSON.stringify(report));
} catch (error) { await page.screenshot({ path: `${evidenceDirectory}/links-failure.png` }); throw error; }
finally { const current = await call('/workspaces/default'); await call('/workspaces/default', { ...original, revision: current.revision }, 'PUT'); await browser.close(); }
