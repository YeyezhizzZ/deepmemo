import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiProxyTarget = process.env.DEEPMEMO_API_PROXY_TARGET ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  publicDir: false,
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          icons: ['lucide-react'],
          react: ['react', 'react-dom'],
        },
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api/v1': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
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
      '/api/knowledge': {
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
