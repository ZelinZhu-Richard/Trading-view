import { browserExecutable, evidenceDirectory } from './browser-runtime.mjs';
import { chromium, expect } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
const browser = await chromium.launch({ executablePath: browserExecutable, headless: true });
const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
const page = await context.newPage(); page.setDefaultTimeout(15000);
const base = 'http://127.0.0.1:8000/api', headers = { 'X-Workbench-Request': '1' };
async function call(path, data, method='POST') { const r = data ? await context.request.fetch(base+path, { method, headers, data }) : await context.request.get(base+path); if (!r.ok()) throw new Error(await r.text()); return r.json(); }
const original = await call('/workspaces/default'), errors = [];
const get = () => call('/workspaces/default');
page.on('pageerror', e => errors.push(e.message));
try {
  const data = await call('/examples/dataset', {}), values = await call(`/datasets/${data.id}`);
  await call('/workspaces/default', { ...original, layout: 1, active_chart: 0, bottom_open: false, charts: original.charts.map(c => ({ ...c, dataset_id: data.id, follow_live: false, drawings: [], indicators: [], kind: 'candlestick', scale: 'linear' })) }, 'PUT');
  await page.goto('http://127.0.0.1:5173/');
  await expect(page.locator('.chart-canvas canvas').first()).toBeVisible();
  const box = await page.locator('.chart-canvas').boundingBox();
  const a = { x: box.x+box.width*.25, y: box.y+box.height*.3 }, b = { x: box.x+box.width*.6, y: a.y };
  await page.getByRole('button', { name: 'Drawing tools', exact: true }).click();
  await page.getByRole('button', { name: 'Horizontal line', exact: true }).click();
  await page.mouse.click(a.x, a.y);
  await expect.poll(async () => (await get()).charts[0].drawings.length).toBe(1);
  const before = (await get()).charts[0].drawings[0];
  await page.mouse.move(b.x, b.y); await page.mouse.down(); await page.mouse.move(b.x+20, b.y+35, { steps: 6 }); await page.mouse.up();
  await expect.poll(async () => (await get()).charts[0].drawings[0].anchors[0].price).not.toBe(before.anchors[0].price);
  const moved = (await get()).charts[0].drawings[0];
  await page.getByRole('button', { name: 'Drawing objects', exact: true }).click();
  await page.getByRole('button', { name: 'Lock drawing Horizontal line', exact: true }).click();
  await page.getByRole('button', { name: 'Close drawing objects', exact: true }).click();
  await page.mouse.move(b.x+20, b.y+35); await page.mouse.down(); await page.mouse.move(b.x+30, b.y+65, { steps: 6 }); await page.mouse.up();
  await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
  if (JSON.stringify((await get()).charts[0].drawings[0].anchors) !== JSON.stringify(moved.anchors)) throw new Error('Locked drawing moved');
  await page.getByRole('button', { name: 'Snap drawing anchors to OHLC', exact: true }).click();
  await page.getByRole('button', { name: 'Drawing tools', exact: true }).click();
  await page.getByRole('button', { name: 'Trend line', exact: true }).click();
  await page.mouse.click(a.x, a.y+110); await page.mouse.click(b.x, b.y+130);
  await expect.poll(async () => (await get()).charts[0].drawings.length).toBe(2);
  const snapped = (await get()).charts[0].drawings[1];
  for (const anchor of snapped.anchors) {
    const bar = values.bars.find(v => v.start === anchor.time);
    if (!bar || ![bar.open,bar.high,bar.low,bar.close].some(p => Math.abs(p-anchor.price)<1e-8)) throw new Error('Snapped anchor is not source OHLC');
  }
  const saved = JSON.stringify((await get()).charts[0].drawings);
  await page.mouse.move(b.x, b.y); await page.mouse.wheel(0,-400);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.getByLabel('Chart interval', { exact: true }).selectOption('1w');
  await expect(page.getByLabel('Chart interval', { exact: true })).toHaveValue('1w');
  await expect(page.locator('.chart-canvas canvas').first()).toBeVisible();
  await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
  if (JSON.stringify((await get()).charts[0].drawings) !== saved) throw new Error('Resize/zoom/interval switch changed stored anchors');
  await page.screenshot({ path: `${evidenceDirectory}/drawing-edges.png` });
  await page.reload();
  await page.getByRole('button', { name: 'Drawing objects', exact: true }).click();
  await expect(page.locator('.drawing-object-list>div')).toHaveCount(2);
  await expect(page.getByRole('button', { name: 'Unlock drawing Horizontal line', exact: true })).toBeVisible();
  if (errors.length) throw new Error(errors.join('\n'));
  const report = { passed: true, browser: await browser.version(), checks: ['whole-object drag away from anchor changes stored price', 'locked drag leaves anchors unchanged', 'OHLC snapping uses actual source prices and times', 'zoom, resize and interval change preserve anchors', 'lock and coordinates survive reload'], errors };
  await writeFile(`${evidenceDirectory}/drawing-edges-report.json`, JSON.stringify(report,null,2)); console.log(JSON.stringify(report));
} catch (error) { await page.screenshot({ path: `${evidenceDirectory}/drawing-edges-failure.png` }); throw error; }
finally { const current = await get(); await call('/workspaces/default', { ...original, revision: current.revision }, 'PUT'); await browser.close(); }
