import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // Always use 5173 (the port the backend's CORS allow-list expects). strictPort
    // makes Vite fail loudly if 5173 is already taken — e.g. by a leftover dev server
    // or another project — instead of silently drifting to 5174/5175.
    strictPort: true,
    proxy: {
      // Proxy API requests to the FastAPI backend during development.
      // The backend runs on port 8000 (uvicorn app.main:app --reload).
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
