import { spawn } from 'node:child_process';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
const label = process.argv[2] ?? 'chrome-final';
if (!/^[a-z0-9-]+$/.test(label)) throw new Error('Invalid evidence label');
const release = label.startsWith('edge') ? JSON.parse(await readFile('.toolchain/edge/verified-release.json', 'utf8')) : null;
const executable = release ? resolve(`.toolchain/edge/expanded/MicrosoftEdge-${release.version}.pkg/Payload/Microsoft Edge.app/Contents/MacOS/Microsoft Edge`) : '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const scripts = process.argv.slice(3).length ? process.argv.slice(3) : ['smoke', 'watchlists', 'indicators', 'drawings', 'alerts', 'python', 'replay', 'research', 'links'];
const runs = []; let owned;
process.on('SIGTERM', () => owned?.kill('SIGTERM'));
process.on('SIGINT', () => owned?.kill('SIGTERM'));
for (const name of scripts) {
  if (!/^[a-z-]+$/.test(name)) throw new Error('Invalid workflow name');
  console.log(`Starting ${label}: ${name}`);
  const began = Date.now();
  const code = await new Promise((resolveCode, reject) => {
    owned = spawn(process.execPath, [`scripts/browser-${name}.mjs`], { cwd: process.cwd(), stdio: 'inherit', env: { ...process.env, WORKBENCH_BROWSER_PATH: executable, WORKBENCH_BROWSER_LABEL: label } });
    owned.on('error', reject); owned.on('exit', resolveCode);
  });
  runs.push({ name, seconds: (Date.now()-began)/1000, code });
  if (code !== 0) break;
}
await mkdir(`evidence/browser/${label}`, { recursive: true });
await writeFile(`evidence/browser/${label}/suite.json`, JSON.stringify({ label, date: new Date().toISOString(), executable, release, runs, passed: runs.length === scripts.length && runs.every(r => r.code === 0) },null,2));
if (runs.some(r => r.code !== 0)) process.exitCode = 1;
