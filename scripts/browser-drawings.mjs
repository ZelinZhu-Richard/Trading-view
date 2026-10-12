import { browserExecutable, evidenceDirectory } from './browser-runtime.mjs';
import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
const output = evidenceDirectory;
await mkdir(output, { recursive: true });
const endpoint = 'http://127.0.0.1:8000/api/workspaces/default';
const browser = await chromium.launch({ executablePath: browserExecutable, headless: true });
const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
const page = await context.newPage();
page.setDefaultTimeout(12000);
const get = async () => (await context.request.get(endpoint)).json();
const put = async value => {
  const response = await context.request.put(endpoint, { headers: { 'X-Workbench-Request': '1' }, data: value });
  if (!response.ok()) throw new Error(await response.text());
};
const original = await get();
const errors = [], results = [];
page.on('pageerror', error => errors.push(error.message));
const tools = [
  ['Trend line', 2], ['Ray', 2], ['Extended line', 2], ['Horizontal line', 1], ['Horizontal ray', 1],
  ['Vertical line', 1], ['Cross line', 1], ['Parallel channel', 3], ['Regression channel', 2], ['Pitchfork', 3],
  ['Fibonacci retracement', 2], ['Fibonacci extension', 3], ['Rectangle', 2], ['Ellipse', 2], ['Triangle', 3],
  ['Brush', 0], ['Path', 0], ['Arrow', 2], ['Text', 1], ['Price range', 2], ['Date range', 2],
  ['Date and price range', 2], ['Long position', 3], ['Short position', 3],
];
try {
  await put({ ...original, layout: 1, active_chart: 0, bottom_open: false,
    charts: original.charts.map((c, i) => i === 0 ? { ...c, drawings: [], indicators: [] } : c) });
  await page.goto('http://127.0.0.1:5173/');
  await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
  await expect(page.locator('.chart-canvas canvas').first()).toBeVisible();
  const box = await page.locator('.chart-canvas').first().boundingBox();
  const a = { x: box.x+box.width*.23, y: box.y+box.height*.3 };
  const b = { x: box.x+box.width*.52, y: box.y+box.height*.2 };
  const c = { x: box.x+box.width*.62, y: box.y+box.height*.45 };
  for (const [name, count] of tools) {
    await page.getByRole('button', { name: 'Drawing tools', exact: true }).click();
    await page.getByRole('button', { name, exact: true }).click();
    if (name === 'Brush') {
      await page.mouse.move(a.x, a.y); await page.mouse.down(); await page.mouse.move(b.x, b.y, { steps: 12 }); await page.mouse.up();
    } else {
      const points = name === 'Long position' ? [a, c, b] : [a, b, c];
      for (const point of points.slice(0, count || 2)) await page.mouse.click(point.x, point.y);
      if (name === 'Path') await page.keyboard.press('Enter');
    }
    await expect(page.getByRole('button', { name: 'Crosshair cursor', exact: true })).toHaveClass(/selected/);
  }
  await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
  const saved = await get();
  if (saved.charts[0].drawings.length !== 24) throw new Error(`Expected 24 drawing families; saved ${saved.charts[0].drawings.length}`);
  results.push('All 24 drawing families created through pointer interaction and saved with time/price anchors.');
  const last = saved.charts[0].drawings.at(-1);
  await page.mouse.move(a.x, a.y); await page.mouse.down(); await page.mouse.move(a.x+35, a.y+18, { steps: 4 }); await page.mouse.up();
  await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
  await expect.poll(async () => JSON.stringify((await get()).charts[0].drawings.find(d => d.id === last.id).anchors)).not.toBe(JSON.stringify(last.anchors));
  const moved = (await get()).charts[0].drawings.find(d => d.id === last.id);
  if (JSON.stringify(moved.anchors) === JSON.stringify(last.anchors)) throw new Error('Anchor drag did not change stored coordinates');
  await page.getByRole('button', { name: 'Undo drawing action', exact: true }).click();
  await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
  await expect.poll(async () => JSON.stringify((await get()).charts[0].drawings.find(d => d.id === last.id).anchors)).toBe(JSON.stringify(last.anchors));
  const undone = (await get()).charts[0].drawings.find(d => d.id === last.id);
  if (JSON.stringify(undone.anchors) !== JSON.stringify(last.anchors)) throw new Error('Undo did not restore the complete anchor edit');
  await page.getByRole('button', { name: 'Redo drawing action', exact: true }).click();
  await page.getByRole('button', { name: 'Drawing objects', exact: true }).click();
  await expect(page.locator('.drawing-object-list>div')).toHaveCount(24);
  await page.getByRole('button', { name: 'Trend line', exact: true }).click();
  await page.getByLabel('Label', { exact: true }).fill('Browser trend');
  await page.getByLabel('Width', { exact: true }).fill('3');
  await page.getByRole('button', { name: 'Save drawing', exact: true }).click();
  await page.getByRole('button', { name: 'Lock drawing Trend line', exact: true }).click();
  await page.getByRole('button', { name: 'Hide drawing Trend line', exact: true }).click();
  await page.getByRole('button', { name: 'Show drawing Trend line', exact: true }).click();
  await page.getByRole('button', { name: 'Duplicate drawing Trend line', exact: true }).click();
  await expect(page.locator('.drawing-object-list>div')).toHaveCount(25);
  await page.locator('.drawing-object-list>div').filter({ hasText: 'Browser trend copy' }).getByRole('button', { name: 'Delete drawing Trend line', exact: true }).click();
  await expect(page.locator('.drawing-object-list>div')).toHaveCount(24);
  await page.screenshot({ path: `${output}/drawing-objects.png` });
  await page.getByRole('button', { name: 'Close drawing objects', exact: true }).click();
  await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
  await page.reload();
  await page.getByRole('button', { name: 'Drawing objects', exact: true }).click();
  await expect(page.locator('.drawing-object-list>div')).toHaveCount(24);
  await expect(page.getByRole('button', { name: 'Unlock drawing Trend line', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Browser trend', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Close drawing objects', exact: true }).click();
  await page.screenshot({ path: `${output}/drawings-all-families.png` });
  results.push('Anchor drag, complete-action undo/redo, label/style edit, lock, hide/show, duplicate/delete and reload persistence passed.');
  if (errors.length) throw new Error(errors.join('\n'));
  await writeFile(`${output}/drawings-report.json`, JSON.stringify({ date: new Date().toISOString(), status: 'passed', browser: await browser.version(), results, pageErrors: errors }, null, 2));
  console.log(JSON.stringify({ status: 'passed', results }));
} catch (error) {
  await page.screenshot({ path: `${output}/drawings-failure.png` });
  await writeFile(`${output}/drawings-report.json`, JSON.stringify({ date: new Date().toISOString(), status: 'failed', error: error.message, results, pageErrors: errors }, null, 2));
  throw error;
} finally {
  await page.close();
  const latest = await get();
  await put({ ...original, revision: latest.revision });
  await browser.close();
}
