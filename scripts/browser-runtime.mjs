import { mkdir } from 'node:fs/promises';
export const browserExecutable = process.env.WORKBENCH_BROWSER_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const label = process.env.WORKBENCH_BROWSER_LABEL;
if (label && !/^[a-z0-9-]+$/.test(label)) throw new Error('Use a simple browser evidence label');
export const evidenceDirectory = label ? `evidence/browser/${label}` : 'evidence/browser';
await mkdir(evidenceDirectory, { recursive: true });
