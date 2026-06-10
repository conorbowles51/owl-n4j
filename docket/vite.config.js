import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Docket is served by the backend under /docket, so the built asset URLs must
// be prefixed accordingly. In dev we proxy /api → the FastAPI backend (8000),
// reusing the same convention as the main frontend. Port 5175 keeps clear of
// v1 (5173) and v2 (5174).
export default defineConfig({
  base: '/docket/',
  plugins: [react()],
  server: {
    port: 5175,
    proxy: {
      '/api': { target: 'http://0.0.0.0:8000', changeOrigin: true },
    },
  },
})
