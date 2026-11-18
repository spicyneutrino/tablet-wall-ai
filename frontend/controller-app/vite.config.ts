import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import type { ProxyOptions } from 'vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vitest/config';

const backend = process.env.CONTROLLER_BACKEND_ORIGIN ?? 'http://127.0.0.1:8000';
const proxy: ProxyOptions = { target: backend, changeOrigin: true, xfwd: false,
  configure(server) {
    server.on('proxyReq', (request) => request.setHeader('Origin', backend));
    server.on('proxyReqWs', (request) => request.setHeader('Origin', backend));
  },
};

export default defineConfig({
  base: '/controller/app/',
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  build: {
    outDir: '../controller/app',
    emptyOutDir: true,
    assetsInlineLimit: 0,
    modulePreload: { polyfill: false },
    cssCodeSplit: false,
  },
  server: {
    proxy: Object.fromEntries([
      '/api', '/devices', '/uploads', '/media', '/assets', '/operator-config',
      '/diagnostics', '/auth', '/healthz', '/ws',
    ].map((path) => [path, { ...proxy, ws: path === '/ws' }])),
  },
  test: { environment: 'node', include: ['src/**/*.test.{ts,tsx}'] },
});
