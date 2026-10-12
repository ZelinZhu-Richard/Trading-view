import { chromium } from 'playwright-core';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const profile = resolve('evidence/browser-profile');
await mkdir(profile, { recursive: true });
const context = await chromium.launchPersistentContext(profile, {
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
  viewport: { width: 1440, height: 960 },
  args: ['--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0'],
});
const port = (await readFile(resolve(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0];
const endpoint = `http://127.0.0.1:${port}`;
await writeFile('evidence/browser-session.json', JSON.stringify({ endpoint, ownerPid: process.pid, startedAt: new Date().toISOString() }, null, 2));
console.log(JSON.stringify({ endpoint, status: 'browser-running' }));
const page = context.pages()[0] ?? await context.newPage();
try {
  await page.goto('https://www.tradingview.com/chart/', { waitUntil: 'domcontentloaded', timeout: 45000 });
  console.log(JSON.stringify({ status: 'reference-loaded', url: page.url(), title: await page.title() }));
} catch (error) {
  console.log(JSON.stringify({ status: 'reference-unavailable', error: error.message }));
}
const close = async () => { await context.close(); process.exit(0); };
process.on('SIGINT', close);
process.on('SIGTERM', close);
await new Promise(() => {});
