import { chromium } from 'playwright-core';
import { readFile, appendFile } from 'node:fs/promises';
const { endpoint } = JSON.parse(await readFile('evidence/browser-session.json', 'utf8'));
const browser = await chromium.connectOverCDP(endpoint);
const page = browser.contexts()[0].pages().find(p => p.url().startsWith('https://www.tradingview.com/chart/'));
if (!page) throw new Error('Owned TradingView reference page is unavailable');
const [action, value, extra] = process.argv.slice(2);
page.setDefaultTimeout(5000);
if (action === 'button') await page.getByRole('button', { name: value, exact: true }).nth(Number(extra ?? 0)).click();
else if (action === 'escape') await page.keyboard.press('Escape');
else if (action === 'text') await page.getByText(value, { exact: true }).first().click();
else if (action === 'hover') await page.getByText(value, { exact: true }).first().hover();
else if (action === 'role') await page.getByRole(extra,{name:value,exact:true}).first().click();
else if (action === 'fill') await page.getByRole(extra ?? 'searchbox').first().fill(value);
else if (action === 'press') await page.keyboard.press(value);
else if (action === 'reload') await page.reload({waitUntil:'domcontentloaded'});
else if (action === 'move' || action === 'click' || action === 'doubleclick') {
  const [x, y] = value.split(',').map(Number);
  await page.mouse[action === 'doubleclick' ? 'dblclick' : action](x, y);
}
else if (action === 'wheel') { const [x,y]=value.split(',').map(Number); await page.mouse.move(750,350); await page.mouse.wheel(x,y); }
else if (action === 'drag') {
  const [x1,y1,x2,y2]=value.split(',').map(Number);
  await page.mouse.move(x1,y1); await page.mouse.down(); await page.mouse.move(x2,y2,{steps:15}); await page.mouse.up();
}
else if (action === 'boxes') console.log(JSON.stringify(await page.locator(value).evaluateAll(elements=>elements.map(e=>({tag:e.tagName,role:e.getAttribute('role'),text:e.textContent.slice(0,80),box:e.getBoundingClientRect().toJSON()})))));
else if (action === 'snapshot') { /* read only */ }
else throw new Error('Unsupported observation step');
const snapshot = await page.locator('body').ariaSnapshot();
await appendFile('evidence/reference-actions.jsonl',JSON.stringify({at:new Date().toISOString(),action,value,extra,snapshot})+'\n');
console.log(snapshot.slice(-26000));
await browser.close();
