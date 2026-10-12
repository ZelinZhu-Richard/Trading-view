import { spawnSync } from 'node:child_process';
const python = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python';
const result = spawnSync(python, ['scripts/generate-contracts.py'], { stdio: 'inherit' });
process.exit(result.status ?? 1);
