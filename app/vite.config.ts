import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  publicDir: 'public',
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api/fs': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/diary': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/assets': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/chat/citations': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/chat/file-references': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
