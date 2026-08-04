/**
 * Vitest keeps its own config because it bundles a rollup-based Vite, while the
 * project builds on Vite 8 / rolldown. Sharing one file makes `tsc -b` fail on
 * incompatible plugin context types.
 *
 * This file is deliberately outside the tsconfig project graph for the same reason.
 */
import { defineConfig } from "vitest/config"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
  },
})
