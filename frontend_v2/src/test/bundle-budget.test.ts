import { describe, expect, it } from "vitest"
import { MAIN_GZIP_MAX, budgetProblem, bundleBudgetPlugin, gzipBytes } from "../../scripts/bundle-budget.js"

// Incompressible bytes of a given gzip size stand in for a built main script.
function scriptOfGzipSize(target: number): Uint8Array {
  const bytes = new Uint8Array(target)
  let x = 0x9e3779b9
  for (let i = 0; i < bytes.length; i++) {
    x ^= x << 13
    x ^= x >>> 17
    x ^= x << 5
    bytes[i] = x & 0xff
  }
  return bytes
}

type Hook = (this: { error: (m: string) => never; info: (m: string) => void }, o: unknown, b: unknown) => void
function runPlugin(code: Uint8Array) {
  const hook = bundleBudgetPlugin().writeBundle as unknown as Hook
  const ctx = { error: (m: string): never => { throw new Error(m) }, info: () => {} }
  const bundle = { "assets/index-x.js": { type: "chunk", isEntry: true, fileName: "assets/index-x.js", code } }
  return () => hook.call(ctx, {}, bundle)
}

describe("the app shell's size gate", () => {
  it("refuses the main script as it was before the shell was split (820,701 gzip bytes on 4 Nov 2026)", () => {
    expect(budgetProblem("index-BvuyZl7x.js", 820_701)).toMatch(/over the shell limit/)
    expect(runPlugin(scriptOfGzipSize(820_701))).toThrow(/over the shell limit of 213,103/)
  })

  it("passes the split shell (193,730 gzip bytes) and holds the limit at that size plus 10 %", () => {
    expect(MAIN_GZIP_MAX).toBe(Math.round(193_730 * 1.1))
    expect(budgetProblem("index.js", 193_730)).toBeNull()
    expect(runPlugin(new TextEncoder().encode("export const a = 1\n".repeat(1000)))).not.toThrow()
  })

  it("measures gzip the way the release stores files", () => {
    const code = scriptOfGzipSize(50_000)
    expect(gzipBytes(code)).toBeGreaterThan(50_000)
    expect(budgetProblem("index.js", MAIN_GZIP_MAX)).toBeNull()
    expect(budgetProblem("index.js", MAIN_GZIP_MAX + 1)).not.toBeNull()
  })
})
