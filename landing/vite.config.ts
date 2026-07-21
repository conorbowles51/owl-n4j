import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
  build: {
    // The immersive Three.js scene is deliberately isolated in its own async chunk.
    chunkSizeWarningLimit: 600,
  },
  server: {
    port: Number(process.env.PORT) || 4178,
  },
})
