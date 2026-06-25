import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { generateBuildName } from './build-name.js'

const buildInfo = generateBuildName()
console.log(`\n  🦉 Build: ${buildInfo.full}\n`)

// Node's http.Server defaults to a 5-minute requestTimeout, which kills
// multi-GB Cellebrite uploads mid-stream. Disable those caps on the dev
// server so the only timeout is the one the frontend XHR enforces.
const liftDevServerTimeouts = {
  name: 'lift-dev-server-timeouts',
  configureServer(server) {
    if (server.httpServer) {
      server.httpServer.requestTimeout = 0
      server.httpServer.headersTimeout = 0
      server.httpServer.timeout = 0
    }
  },
}

export default defineConfig({
  plugins: [react(), liftDevServerTimeouts],
  define: {
    __BUILD_NAME__: JSON.stringify(buildInfo.displayName),
    __BUILD_COMMIT__: JSON.stringify(buildInfo.commit),
    __BUILD_TIMESTAMP__: JSON.stringify(buildInfo.timestamp),
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://0.0.0.0:8000',
        changeOrigin: true,
        // http-proxy's own response timeout — disable so it never
        // out-times the XHR on slow backend processing.
        proxyTimeout: 0,
        timeout: 0,
      },
      // Resumable evidence uploads -> tusd (127.0.0.1:1080). Same origin as
      // the app, so the browser/Uppy never crosses CORS. xfwd:true adds the
      // X-Forwarded-* headers tusd needs (it runs with -behind-proxy) to
      // build correct absolute upload URLs in its Location header. Timeouts
      // disabled like /api so long uploads aren't cut off (chunks are small,
      // but a slow link on a big file can still hold a chunk a while).
      '/files': {
        target: 'http://127.0.0.1:1080',
        changeOrigin: true,
        xfwd: true,
        proxyTimeout: 0,
        timeout: 0,
      },
    },
  },
})
