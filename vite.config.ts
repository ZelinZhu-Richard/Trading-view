import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({ plugins: [react()], optimizeDeps: { include: [
  '@monaco-editor/react', 'monaco-editor/esm/vs/editor/editor.api',
  'monaco-editor/esm/vs/basic-languages/python/python.contribution',
] }, server: {
  host: '127.0.0.1', port: 5173, strictPort: true,
  proxy: { '/api': { target: 'http://127.0.0.1:8000', ws: true } },
} });
