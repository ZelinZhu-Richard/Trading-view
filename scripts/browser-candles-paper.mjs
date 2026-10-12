import { browserExecutable, evidenceDirectory } from './browser-runtime.mjs';
import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
await mkdir(evidenceDirectory, { recursive: true });
const browser = await chromium.launch({ executablePath: browserExecutable, headless: true });
const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
const page = await context.newPage(); page.setDefaultTimeout(25000);
const base = 'http://127.0.0.1:8000/api', headers = { 'X-Workbench-Request': '1' };
async function call(path, data, method='POST') {
  const response = data ? await context.request.fetch(base+path, { method, headers, data }) : await context.request.get(base+path);
  if (!response.ok()) throw new Error(await response.text());
  return response.json();
}
const original = await call('/workspaces/default'), errors = [], messages = [];
let accountId, dataset, fresh, filled, submitted;
page.on('pageerror', error => errors.push(error.message));
page.on('websocket', socket => { if (socket.url().includes('/candles/events')) socket.on('framereceived', frame => { try { const v = JSON.parse(frame.payload); if (v.type === 'candles') messages.push({ time: Date.now(), states: Object.values(v.states).map(s => ({ status: s.status, id: s.dataset.id, count: s.dataset.row_count })) }); } catch {} }); });
try {
  const instruments = await call('/providers/coinbase/instruments?query=BTC-USD');
  const instrument = instruments.find(v => v.symbol === 'BTC-USD');
  if (!instrument) throw new Error('Coinbase BTC-USD discovery failed');
  const now = Math.floor(Date.now()/60000)*60;
  dataset = await call('/history', { provider: 'coinbase', instrument, interval: '1m', start: now-12*60, end: now-5*60 });
  await call('/workspaces/default', { ...original, layout: 1, active_chart: 0, bottom_open: true, bottom_height: 350, theme: 'light', charts: original.charts.map(c => ({ ...c, dataset_id: dataset.id, follow_live: false, drawings: [], indicators: [] })) }, 'PUT');
  await page.goto('http://127.0.0.1:5173/');
  await page.getByLabel('Follow provider candles').check();
  await expect(page.locator('.candle-status')).toContainText('Completed candles · checked', { timeout: 60000 });
  await expect.poll(async () => {
    const status = await call('/candles'); fresh = status.series.find(s => s.dataset.first_start === dataset.first_start && s.dataset.instrument.id === instrument.id); return fresh?.dataset.row_count ?? 0;
  }, { timeout: 60000 }).toBeGreaterThan(dataset.row_count);
  await expect(page.locator('.instrument-details')).toContainText(String(fresh.dataset.row_count));
  await page.getByRole('button', { name: 'Replay & paper', exact: true }).click();
  await page.getByRole('button', { name: 'New account', exact: true }).click();
  await page.getByLabel('Account name', { exact: true }).fill(`Coinbase refresh browser ${Date.now()}`);
  await page.getByLabel('Account mode', { exact: true }).selectOption('paper');
  const created = page.waitForResponse(r => r.url().endsWith('/api/accounts') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  accountId = (await (await created).json()).account.id;
  await page.getByLabel('Simulated order quantity').fill('0.0001');
  const ordered = page.waitForResponse(r => r.url().endsWith(`/accounts/${accountId}/orders`) && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Place simulated order', exact: true }).click();
  submitted = (await (await ordered).json()).orders.at(-1);
  await expect(page.locator('.account-tables')).toContainText('pending');
  console.log(JSON.stringify({ stage: 'waiting-for-real-completed-bar', accountId, submittedAt: submitted.submitted_at, earliestOpening: submitted.eligible_from }));
  await expect.poll(async () => { filled = await call(`/accounts/${accountId}`); return filled.fills.length; }, { timeout: 240000, intervals: [2000, 5000] }).toBeGreaterThan(0);
  if (filled.fills[0].time < submitted.submitted_at || Number(filled.fills[0].quantity) !== .0001) throw new Error('Paper fill violates actual-time eligibility');
  await expect(page.locator('.account-tables')).toContainText('filled');
  await page.getByRole('button', { name: 'fills', exact: true }).click();
  await expect(page.locator('.account-tables tbody tr')).toHaveCount(1);
  await page.screenshot({ path: `${evidenceDirectory}/candles-paper-1280-light.png` });
  await page.getByRole('button', { name: 'Pause paper updates', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Resume paper updates', exact: true })).toBeVisible();
  await page.getByLabel('Follow provider candles').uncheck();
  await expect.poll(async () => (await call('/workspaces/default')).charts[0].follow_live).toBe(false);
  const frozenId = (await call('/workspaces/default')).charts[0].dataset_id;
  await page.reload();
  await expect(page.getByLabel('Follow provider candles')).not.toBeChecked();
  await page.getByRole('button', { name: 'Replay & paper', exact: true }).click();
  await page.getByLabel('Saved simulated account').selectOption(accountId);
  await expect(page.getByRole('button', { name: 'Resume paper updates', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'fills', exact: true }).click();
  await expect(page.locator('.account-tables tbody tr')).toHaveCount(1);
  if (errors.length) throw new Error(errors.join('\n'));
  const report = { passed: true, kind: 'actual Coinbase public data / simulated local orders', datasetId: dataset.id, initialBars: dataset.row_count, refreshedDatasetId: fresh.dataset.id, refreshedBars: fresh.dataset.row_count, accountId, submitted, fill: filled.fills[0], frozenId, checks: ['visible chart subscription catches up real completed candles', 'paper fill waits for an opening at or after actual submission time', 'same provider history advances chart and account', 'pause and follow-off persist', 'reopen preserves filled account'], websocketMessages: messages.length, errors };
  await writeFile(`${evidenceDirectory}/candles-paper-report.json`, JSON.stringify(report, null, 2)+'\n');
  console.log(JSON.stringify(report));
} finally {
  if (accountId) {
    for (let attempt=0; attempt<3; attempt++) { try { const state = await call(`/accounts/${accountId}`); await call(`/accounts/${accountId}/pause`, { revision: state.account.revision, paused: true }); break; } catch (error) { if (attempt === 2) console.error('Pause test account:', String(error)); } }
  }
  const latest = await call('/workspaces/default'); await call('/workspaces/default', { ...original, revision: latest.revision }, 'PUT');
  await browser.close();
}
