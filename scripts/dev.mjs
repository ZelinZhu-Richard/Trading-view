import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
const python = resolve(process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
if (!existsSync(python)) throw new Error('Run uv sync to create the project Python environment first.');
const children = [
  spawn(python, ['-m', 'uvicorn', 'backend.app:app', '--host', '127.0.0.1', '--port', '8000', '--reload', '--reload-dir', 'backend'], { stdio: 'inherit' }),
  spawn(process.execPath, ['node_modules/vite/bin/vite.js'], { stdio: 'inherit' }),
];
let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  children.forEach(child => { if (child.exitCode === null) child.kill('SIGTERM'); });
  setTimeout(() => {
    children.forEach(child => { if (child.exitCode === null) child.kill('SIGKILL'); });
    process.exit(code);
  }, 2500).unref();
}
children.forEach(child => child.on('exit', code => stop(code ?? 1)));
process.on('SIGINT', () => stop());
process.on('SIGTERM', () => stop());
