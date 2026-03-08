import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { generateBuildName } from './build-name.js'

const buildInfo = generateBuildName()
console.log(`\n  🦉 Build: ${buildInfo.full}\n`)

export default defineConfig({
  plugins: [react()],
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
      },
    },
  },
})
