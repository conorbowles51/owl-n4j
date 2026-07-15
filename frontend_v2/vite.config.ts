import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import path from "path"
import { generateBuildName } from "./build-name.js"

const buildInfo = generateBuildName()
const frontendPort = Number(process.env.FRONTEND_PORT || "5174")
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || "http://0.0.0.0:8002"
const apiProxyTimeout = Number(process.env.VITE_API_PROXY_TIMEOUT_MS || "3600000")
console.log(`\n  🦉 Build: ${buildInfo.full}\n`)

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Timeline is lazy-loaded, so its virtualizer may otherwise be discovered
  // after the dev server has already served modules. Pre-bundle it at startup
  // to avoid Vite invalidating the first Timeline import with a 504.
  optimizeDeps: {
    include: ["@tanstack/react-virtual"],
  },
  define: {
    __BUILD_NAME__: JSON.stringify(buildInfo.displayName),
    __BUILD_COMMIT__: JSON.stringify(buildInfo.commit),
    __BUILD_TIMESTAMP__: JSON.stringify(buildInfo.timestamp),
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: frontendPort,
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
        ws: true,
        timeout: apiProxyTimeout,
        proxyTimeout: apiProxyTimeout,
      },
    },
  },
})
