import { defineConfig, type ProxyOptions } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import path from "path"
import { generateBuildName } from "./build-name.js"

const buildInfo = generateBuildName()
const frontendPort = Number(process.env.FRONTEND_PORT || "5174")
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || "http://0.0.0.0:8002"
const apiProxyTimeout = Number(process.env.VITE_API_PROXY_TIMEOUT_MS || "3600000")
// The browser's address for the activity trail. The backend sees only this
// proxy (127.0.0.1), so the proxy states the client socket's address:
// X-Real-IP is overwritten (a browser cannot supply its own) and
// X-Forwarded-For gets the socket address appended (xfwd). The backend
// believes them only from loopback.
const setRealIp = (
  proxyReq: { setHeader(name: string, value: string): void },
  req: { socket?: { remoteAddress?: string } }
) => {
  const address = req.socket?.remoteAddress
  if (address) proxyReq.setHeader("x-real-ip", address)
}
const apiProxy: Record<string, ProxyOptions> = {
  "/api": {
    target: apiProxyTarget,
    changeOrigin: true,
    ws: true,
    xfwd: true,
    timeout: apiProxyTimeout,
    proxyTimeout: apiProxyTimeout,
    configure: (proxy) => {
      proxy.on("proxyReq", setRealIp)
      proxy.on("proxyReqWs", setRealIp)
    },
  },
}
console.log(`\n  🦉 Build: ${buildInfo.full}\n`)

// Written into dist/ so a running tab can detect that a newer build has been
// deployed (stale open SPA tabs otherwise survive every deploy).
const versionJsonPlugin: import("vite").Plugin = {
  name: "emit-version-json",
  generateBundle() {
    this.emitFile({
      type: "asset",
      fileName: "version.json",
      source: JSON.stringify({
        commit: buildInfo.commit,
        name: buildInfo.displayName,
        timestamp: buildInfo.timestamp,
      }),
    })
  },
}

export default defineConfig({
  plugins: [react(), tailwindcss(), versionJsonPlugin],
  // Pre-bundle dependencies used by lazy views so their first activation does
  // not invalidate the running dev server.
  optimizeDeps: {
    include: [
      "@tanstack/react-virtual",
      "react-force-graph-3d",
      "three-spritetext",
      "sonner",
      "react-markdown",
      "remark-gfm",
      "@testing-library/user-event",
    ],
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
    proxy: apiProxy,
  },
  // The deployed service serves the compiled bundle. Keeping the same proxy
  // here preserves the frontend's relative /api URLs and WebSocket endpoint.
  preview: {
    port: frontendPort,
    proxy: apiProxy,
  },
})
