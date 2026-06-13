import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Respect a port assigned by tooling (e.g. preview harness); fall back to Vite default.
    port: Number(process.env.PORT) || 5173,
  },
})
