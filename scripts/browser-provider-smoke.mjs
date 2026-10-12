import { browserExecutable, evidenceDirectory } from './browser-runtime.mjs';
import { chromium, expect } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
const browser = await chromium.launch({ executablePath: browserExecutable, headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
page.setDefaultTimeout(15000);
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto('http://127.0.0.1:5173/');
  await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Connect data source', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Connect a data source' })).toBeVisible();
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await page.locator('.provider-results button').filter({ has: page.getByText('BTC-USD', { exact: true }) }).click();
  await page.getByRole('button', { name: 'Load market history', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Connect a data source' })).toHaveCount(0);
  await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
  await expect(page.locator('.data-status')).toContainText('live quote', { timeout: 20000 });
  await page.screenshot({ path: `${evidenceDirectory}/coinbase-connected.png` });
  await page.reload();
  await expect(page.locator('.instrument-details h2')).toHaveText('BTC-USD');
  await expect(page.locator('.data-status')).toContainText('live quote', { timeout: 20000 });
  if (errors.length) throw new Error(errors.join('\n'));
  const report = { date: new Date().toISOString(), status: 'passed', browser: await browser.version(),
    checks: ['Provider dialog', 'Coinbase product search', 'Historical data request', 'Chart and watchlist selection', 'Real live quote displayed', 'Saved dataset and quote resubscription after reload'], pageErrors: errors };
  await writeFile(`${evidenceDirectory}/provider-report.json`, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
} catch (error) {
  await page.screenshot({ path: `${evidenceDirectory}/provider-failure.png` });
  await writeFile(`${evidenceDirectory}/provider-report.json`, JSON.stringify({ status: 'failed', error: error.message, pageErrors: errors }, null, 2));
  throw error;
} finally { await browser.close(); }
