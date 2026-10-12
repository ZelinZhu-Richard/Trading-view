import { browserExecutable, evidenceDirectory } from './browser-runtime.mjs';
import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
await mkdir(evidenceDirectory, { recursive: true });
const browser = await chromium.launch({ executablePath: browserExecutable, headless: true });
const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
const page = await context.newPage(); page.setDefaultTimeout(25000);
const base = 'http://127.0.0.1:8000/api', headers = { 'X-Workbench-Request': '1' };
const original = await (await context.request.get(base+'/workspaces/default')).json();
const stamp = Date.now(), errors = [], dataChecks = [], studyChecks = [];
let accountId, scriptId, jobId;
page.on('pageerror', e => errors.push(e.message));
page.on('response', async response => {
  try {
    if (response.url().includes('/api/datasets/') && response.url().includes('?cutoff=') && response.ok()) {
      const cutoff = Number(new URL(response.url()).searchParams.get('cutoff'));
      const data = await response.json(); dataChecks.push({ cutoff, count: data.bars.length, maxEnd: Math.max(...data.bars.map(b => b.end)) });
    }
    if (response.url().endsWith('/api/indicators/calculate') && response.ok()) {
      const request = response.request().postDataJSON(); if (request.cutoff != null) { const data = await response.json(); studyChecks.push({ cutoff: request.cutoff, maxEnd: Math.max(...data.available_at) }); }
    }
  } catch { /* Requests intentionally aborted while a newer cursor replaces them. */ }
});
try {
  const dataset = await (await context.request.post(base+'/examples/dataset', { headers })).json();
  const source = await (await context.request.get(base+`/datasets/${dataset.id}`)).json();
  const cursor = source.bars[4].end;
  await context.request.put(base+'/workspaces/default', { headers, data: { ...original, bottom_open: true, bottom_height: 420, layout: 4, active_chart: 0, charts: original.charts.map((c, i) => ({ ...c, dataset_id: dataset.id, drawings: [], indicators: [{ schema_version: 1, id: 'replay-mean-'+i, definition_id: 'sma', parameters: { length: 2 }, visible: true, color: '#54b4df', width: 2, pane: 0 }] })) } });
  scriptId = crypto.randomUUID();
  await context.request.put(base+`/scripts/${scriptId}`, { headers, data: { schema_version: 1, id: scriptId, name: `Replay strategy ${stamp}`, kind: 'strategy', source: 'def initialize(ctx):\n    ctx.order(ctx.subscriptions[0], "buy", 1)\n\ndef on_bars(ctx, bars):\n    assert all(bar.end <= ctx.timestamp for bar in ctx.history(ctx.subscriptions[0]))\n    ctx.log(ctx.timestamp)', parameters: {}, subscriptions: [], revision: 0 } });
  await page.goto('http://127.0.0.1:5173/');
  await page.getByRole('button', { name: 'Replay & paper', exact: true }).click();
  await page.getByRole('button', { name: 'New account', exact: true }).click();
  await page.getByLabel('Account name', { exact: true }).fill(`Replay browser ${stamp}`);
  await page.getByLabel('Initial replay cursor UTC', { exact: true }).fill(new Date(cursor*1000).toISOString().slice(0, 16));
  await page.getByLabel('Allow labeled synthetic demonstration data').check();
  const created = page.waitForResponse(r => r.url().endsWith('/api/accounts') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  accountId = (await (await created).json()).account.id;
  await expect(page.locator('.replay-banner')).toContainText('HISTORICAL REPLAY');
  await expect(page.locator('.chart-tile .chart-canvas')).toHaveCount(4);
  await expect.poll(() => dataChecks.filter(c => c.cutoff === cursor).length).toBeGreaterThanOrEqual(4);
  await expect.poll(() => studyChecks.filter(c => c.cutoff === cursor).length).toBeGreaterThanOrEqual(4);
  await expect(page.locator('.instrument-details .data-status')).toContainText('Replay');
  await page.getByLabel('Simulated order quantity').fill('2');
  await page.getByRole('button', { name: 'Place simulated order', exact: true }).click();
  await expect(page.locator('.account-tables')).toContainText('pending');
  await page.getByRole('button', { name: 'Step replay one bar', exact: true }).click();
  await expect(page.locator('.account-tables')).toContainText('filled');
  const filled = await (await context.request.get(base+`/accounts/${accountId}`)).json();
  if (filled.fills.length !== 1 || Number(filled.fills[0].quantity) !== 2 || filled.fills[0].price !== String(source.bars[5].open.toFixed(2))) throw new Error('Replay fill differs from shared source opening price');
  await page.getByLabel('Replay speed', { exact: true }).selectOption('10');
  await page.getByRole('button', { name: 'Play replay', exact: true }).click();
  await expect.poll(async () => (await (await context.request.get(base+`/accounts/${accountId}`)).json()).account.cursor).toBeGreaterThan(filled.account.cursor);
  await page.getByRole('button', { name: 'Pause replay', exact: true }).click();
  await expect(page.locator('.replay-controls')).not.toContainText('updating…');
  const paused = (await (await context.request.get(base+`/accounts/${accountId}`)).json()).account.cursor;
  await page.waitForTimeout(500);
  if ((await (await context.request.get(base+`/accounts/${accountId}`)).json()).account.cursor !== paused) throw new Error('Paused replay continued advancing');
  const earlier = source.bars[1].end;
  await page.getByLabel('Replay cursor UTC', { exact: true }).fill(new Date(earlier*1000).toISOString().slice(0, 16));
  await page.getByRole('button', { name: 'Seek', exact: true }).click();
  await expect.poll(async () => (await (await context.request.get(base+`/accounts/${accountId}`)).json()).account.cursor).toBe(earlier);
  const reset = await (await context.request.get(base+`/accounts/${accountId}`)).json();
  if (reset.fills.length || reset.portfolio.positions.length || reset.account.commands.length) throw new Error('Backward seek retained future account state');
  await expect.poll(() => dataChecks.filter(c => c.cutoff === earlier).length).toBeGreaterThanOrEqual(4);
  await page.screenshot({ path: `${evidenceDirectory}/replay-four-charts.png` });
  await page.getByRole('button', { name: 'Python editor', exact: true }).click();
  await page.getByLabel('Saved Python script').selectOption(scriptId);
  await expect(page.getByText('Syntax and declarations valid', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Run settings', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Run strategy to replay cursor', exact: true })).toBeVisible();
  await expect(page.getByLabel('Run end UTC', { exact: true })).toBeDisabled();
  const run = page.waitForResponse(r => r.url().endsWith('/api/research') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Run', exact: true }).click();
  jobId = (await (await run).json()).id;
  await expect(page.locator('.job-status')).toHaveText('completed', { timeout: 30000 });
  const result = await (await context.request.get(base+`/research/${jobId}/result`)).json();
  if (result.settings.end !== earlier || result.final_portfolio.time !== earlier || result.fills.some(f => f.time > earlier)) throw new Error('Strategy crossed replay cutoff');
  await page.reload();
  await page.getByRole('button', { name: 'Replay & paper', exact: true }).click();
  await page.getByLabel('Saved simulated account').selectOption(accountId);
  await expect(page.locator('.replay-banner')).toBeVisible();
  await expect(page.getByLabel('Replay cursor UTC', { exact: true })).toHaveValue(new Date(earlier*1000).toISOString().slice(0, 16));
  await page.getByRole('button', { name: 'Exit replay', exact: true }).click();
  await expect(page.locator('.replay-banner')).toHaveCount(0);
  if (dataChecks.some(c => c.maxEnd > c.cutoff) || studyChecks.some(c => c.maxEnd > c.cutoff)) throw new Error('A chart/study response exposed values after its cursor');
  if (errors.length) throw new Error(JSON.stringify(errors));
  const report = { status: 'passed', date: new Date().toISOString(), browser: await browser.version(), accountId, jobId,
    dataChecks, studyChecks, pageErrors: errors, results: ['Four-chart causal cutoff, shared SMA cutoff, manual next-open fill, step/play/pause/speed, backward reset, strategy run capped at cursor, saved account reopen and exit replay passed.'],
    limitations: ['Synthetic prices; current-market paper refresh has separate backend evidence and is not exercised by this browser check.'] };
  await writeFile(`${evidenceDirectory}/replay-report.json`, JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ ...report, dataChecks: dataChecks.length, studyChecks: studyChecks.length }));
} catch (error) {
  await page.screenshot({ path: `${evidenceDirectory}/replay-failure.png` });
  await writeFile(`${evidenceDirectory}/replay-report.json`, JSON.stringify({ status: 'failed', error: error.message, pageErrors: errors, accountId, jobId, dataChecks, studyChecks }, null, 2));
  throw error;
} finally {
  await page.close();
  if (jobId) await context.request.post(base+`/research/${jobId}/cancel`, { headers });
  if (scriptId) await context.request.delete(base+`/scripts/${scriptId}`, { headers });
  const latest = await (await context.request.get(base+'/workspaces/default')).json();
  await context.request.put(base+'/workspaces/default', { headers, data: { ...original, revision: latest.revision } });
  await browser.close();
}
