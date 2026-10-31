import { defineConfig, type ProxyOptions } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import path from "path"
import fs from "fs"
import { buildDisplayName, generateBuildId } from "./build-name.js"

const buildId = generateBuildId()
const buildName = buildDisplayName(buildId)
// Raised (in this file) when a backend change needs every open tab to reload. The file is part of the frontend tree,
// so raising it gives a new build id, and the stale-tab guard shows the reload banner.
const apiCompat = fs.readFileSync(path.resolve(__dirname, "api-compat.txt"), "utf-8").trim()
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
console.log(`\n  🦉 Build: ${buildName} (${buildId.substring(0, 12)})\n`)

// The build id lives only in index.html (a <meta> tag) and version.json, never in a JavaScript file: index.html is
// served no-cache, so a release that does not change the frontend keeps every hashed file name and every browser
// cache entry. version.json lets a running tab detect that a different build is now served (stale open SPA tabs
// otherwise survive every deploy). "commit" repeats the build id for tabs opened before this change, whose guard
// compares that field.
const buildIdentityPlugin: import("vite").Plugin = {
  name: "loupe-build-identity",
  transformIndexHtml() {
    return [
      { tag: "meta", attrs: { name: "loupe-build", content: buildId }, injectTo: "head" },
      { tag: "meta", attrs: { name: "loupe-build-name", content: buildName }, injectTo: "head" },
    ]
  },
  generateBundle() {
    this.emitFile({
      type: "asset",
      fileName: "version.json",
      source: JSON.stringify({ build: buildId, commit: buildId, name: buildName, api_compat: apiCompat }),
    })
  },
}

export default defineConfig({
  plugins: [react(), tailwindcss(), buildIdentityPlugin],
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
