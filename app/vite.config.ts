import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiProxyTarget = process.env.DEEPMEMO_API_PROXY_TARGET ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  publicDir: 'public',
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api/fs': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      '/api/diary': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      '/assets': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      '/api/chat/citations': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      '/api/chat/file-references': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
