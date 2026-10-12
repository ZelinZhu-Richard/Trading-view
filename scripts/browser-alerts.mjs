import { browserExecutable, evidenceDirectory } from './browser-runtime.mjs';
import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
await mkdir(evidenceDirectory, { recursive: true });
const endpoint = 'http://127.0.0.1:8000/api';
const browser = await chromium.launch({ executablePath: browserExecutable, headless: true });
const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
const page = await context.newPage();
page.setDefaultTimeout(15000);
const request = async (path, data, method='POST') => {
  const response = data || method === 'DELETE' ? await context.request.fetch(endpoint+path, { method, headers: { 'X-Workbench-Request': '1' }, data }) : await context.request.get(endpoint+path);
  if (!response.ok()) throw new Error(await response.text());
  return response.json();
};
const original = await request('/workspaces/default');
const runId = Date.now();
const name = `Browser crossing ${runId}`;
const errors = [], results = [];
let alertId;
page.on('pageerror', error => errors.push(error.message));
async function load(closes) {
  const preview = await request('/imports/preview', { interval: '1m', timezone: 'UTC',
    instrument: { id: `EXAMPLE:ALERTBROWSER-${runId}`, symbol: 'ALERTBROWSER', name: 'Synthetic alert browser fixture', exchange: 'EXAMPLE', asset_class: 'other', quote_currency: 'USD', timezone: 'UTC', calendar: '24/7' },
    csv_text: 'timestamp,open,high,low,close,volume\n'+closes.map((c, i) => `${new Date(Date.UTC(2025,0,1,0,i)).toISOString()},${c},${c+1},${c-1},${c},1`).join('\n') });
  if (!preview.can_commit) throw new Error(JSON.stringify(preview.errors));
  return request('/imports/commit', { token: preview.token });
}
try {
  const data = await load([9,10]);
  await request('/workspaces/default', { ...original, layout: 1, active_chart: 0,
    charts: original.charts.map((c, i) => i === 0 ? { ...c, dataset_id: data.id } : c) }, 'PUT');
  await page.goto('http://127.0.0.1:5173/');
  await page.getByRole('button', { name: 'Local alerts', exact: true }).click();
  await expect(page.getByText('Evaluation running', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'New alert', exact: true }).click();
  await page.getByLabel('Name', { exact: true }).fill(name);
  await page.getByLabel('Threshold', { exact: true }).fill('10');
  await page.getByLabel('Repeat on matching completed bars', { exact: true }).check();
  await page.getByRole('button', { name: 'Save alert', exact: true }).click();
  await expect(page.locator('.alert-rule-name').filter({ hasText: name })).toBeVisible();
  alertId = (await request('/alerts')).find(a => a.name === name).id;
  await page.getByRole('button', { name: 'Close alerts', exact: true }).click();
  await load([9,10,11,9,12]);
  await expect(page.locator('.alert-toast')).toContainText(name);
  await page.getByRole('button', { name: 'Dismiss alert notification', exact: true }).click();
  await page.getByRole('button', { name: 'Local alerts', exact: true }).click();
  await page.getByRole('button', { name: new RegExp('^Trigger history') }).click();
  await expect(page.locator('tbody tr').filter({ hasText: name })).toHaveCount(2);
  await page.screenshot({ path: `${evidenceDirectory}/alert-history.png` });
  results.push('Created recurring completed-price crossing alert in UI; importing two new crossings produced two stored events and an in-app notification.');
  await page.getByRole('button', { name: new RegExp('^Alert rules') }).click();
  await page.getByRole('button', { name: `Pause alert ${name}`, exact: true }).click();
  await expect(page.getByRole('button', { name: `Resume alert ${name}`, exact: true })).toBeVisible();
  await page.getByRole('button', { name: `Resume alert ${name}`, exact: true }).click();
  await expect(page.getByRole('button', { name: `Pause alert ${name}`, exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Close alerts', exact: true }).click();
  await page.reload();
  await page.getByRole('button', { name: 'Local alerts', exact: true }).click();
  await expect(page.locator('.alert-rule-name').filter({ hasText: name })).toBeVisible();
  await page.getByRole('button', { name: new RegExp('^Trigger history') }).click();
  await expect(page.locator('tbody tr').filter({ hasText: name })).toHaveCount(2);
  results.push('Pause/resume, reload persistence and repeated-evaluation deduplication passed.');
  if (errors.length) throw new Error(errors.join('\n'));
  await writeFile(`${evidenceDirectory}/alerts-report.json`, JSON.stringify({ date: new Date().toISOString(), status: 'passed', browser: await browser.version(), results, pageErrors: errors }, null, 2));
  console.log(JSON.stringify({ status: 'passed', results }));
} catch (error) {
  await page.screenshot({ path: `${evidenceDirectory}/alerts-failure.png` });
  await writeFile(`${evidenceDirectory}/alerts-report.json`, JSON.stringify({ date: new Date().toISOString(), status: 'failed', error: error.message, results, pageErrors: errors }, null, 2));
  throw error;
} finally {
  await page.close();
  if (alertId) await request(`/alerts/${alertId}`, undefined, 'DELETE');
  const latest = await request('/workspaces/default');
  await request('/workspaces/default', { ...original, revision: latest.revision }, 'PUT');
  await browser.close();
}
