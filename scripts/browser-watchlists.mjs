import { browserExecutable, evidenceDirectory } from './browser-runtime.mjs';
import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
const output = evidenceDirectory;
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ executablePath: browserExecutable, headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
page.setDefaultTimeout(10000);
const errors = [], results = [];
page.on('pageerror', error => errors.push(error.message));
const ownedName = `Watchlist check ${Date.now()}`;
let originalList;
const manage = async name => {
  await page.getByRole('button', { name: 'Manage watchlists', exact: true }).click();
  await page.getByRole('button', { name, exact: true }).click();
};
try {
  await page.goto('http://127.0.0.1:5173/');
  await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
  originalList = await page.getByLabel('Active watchlist', { exact: true }).inputValue();
  await manage('New list');
  await page.getByLabel('Watchlist name', { exact: true }).fill(ownedName);
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await manage('Add section');
  await page.getByLabel('Section name', { exact: true }).fill('Research');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.getByLabel('Add instrument to watchlist', { exact: true }).selectOption({ index: 1 });
  const known = await page.locator('.watchlist-select').first().getAttribute('aria-label');
  const symbol = known.split(',')[0];
  await page.locator('.watchlist-row').first().hover();
  await page.getByRole('button', { name: `Choose section for ${symbol}`, exact: true }).click();
  await page.getByLabel(`Section for ${symbol}`, { exact: true }).selectOption('Research');
  await page.getByRole('button', { name: 'Rename section Research', exact: true }).click();
  await page.getByLabel('Section name', { exact: true }).fill('Core');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Rename section Core', exact: true })).toBeVisible();
  const csv = 'instrument_id,section\n' + Array.from({ length: 1200 }, (_, i) => `CHECK:${String(i).padStart(4, '0')},Long list`).join('\n');
  await page.getByLabel('Watchlist CSV', { exact: true }).setInputFiles({ name: 'long-list.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) });
  await expect(page.getByText('1201 INSTRUMENTS', { exact: true })).toBeVisible();
  const rendered = await page.locator('.watchlist-row').count();
  if (rendered > 12) throw new Error(`Expected virtualized rows, got ${rendered}`);
  await page.getByLabel('Search watchlist', { exact: true }).fill('CHECK:1199');
  await expect(page.locator('.watchlist-row')).toHaveCount(1);
  await expect(page.locator('.watchlist-select')).toBeDisabled();
  await page.getByLabel('Search watchlist', { exact: true }).fill('');
  await page.getByLabel('Watchlist sort', { exact: true }).selectOption('symbol');
  await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
  const selected = await page.getByLabel('Active watchlist', { exact: true }).inputValue();
  await page.reload();
  await expect(page.getByLabel('Active watchlist', { exact: true })).toHaveValue(selected);
  await expect(page.getByLabel('Watchlist sort', { exact: true })).toHaveValue('symbol');
  await expect(page.getByText('1201 INSTRUMENTS', { exact: true })).toBeVisible();
  results.push(`List creation, addition, section assignment/rename, CSV import, unavailable identities, filter, sorting and save/reload passed; ${rendered} rendered rows for 1,201 instruments.`);
  const downloaded = page.waitForEvent('download');
  await manage('Export CSV');
  const download = await downloaded;
  const stream = await download.createReadStream(); let exported = '';
  for await (const chunk of stream) exported += chunk.toString();
  if (!exported.includes('CHECK:1199') || !exported.includes(',Core,')) throw new Error('CSV export lost identities or sections');
  await page.screenshot({ path: `${output}/watchlists.png` });
  if (errors.length) throw new Error(errors.join('\n'));
  results.push('CSV export preserved all identities and assigned sections.');
  await writeFile(`${output}/watchlists-report.json`, JSON.stringify({ date: new Date().toISOString(), browser: await browser.version(), status: 'passed', results, pageErrors: errors }, null, 2));
  console.log(JSON.stringify({ status: 'passed', results }));
} catch (error) {
  await page.screenshot({ path: `${output}/watchlists-failure.png` });
  await writeFile(`${output}/watchlists-report.json`, JSON.stringify({ date: new Date().toISOString(), status: 'failed', results, error: error.message, pageErrors: errors }, null, 2));
  throw error;
} finally {
  const owned = page.getByLabel('Active watchlist', { exact: true }).locator('option').filter({ hasText: ownedName });
  if (await owned.count()) {
    await page.getByLabel('Active watchlist', { exact: true }).selectOption(await owned.first().getAttribute('value'));
    await manage('Delete list');
    if (originalList) await page.getByLabel('Active watchlist', { exact: true }).selectOption(originalList);
    await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
  }
  await browser.close();
}
