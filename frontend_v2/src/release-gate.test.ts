import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

/**
 * The release builds with `npm run build` (deploy/frontend-release.sh). That build is the gate: it type-checks, then
 * refuses any eslint problem (error or warning), then bundles. A commit with lint problems cannot be released.
 */
describe("release build gate", () => {
  const pkg = JSON.parse(readFileSync(resolve(__dirname, "../package.json"), "utf8")) as { scripts: Record<string, string> }
  const steps = pkg.scripts.build.split("&&").map((s) => s.trim())

  it("type-checks, then lints with no problem allowed, then bundles", () => {
    expect(steps[0]).toBe("tsc -b")
    expect(steps).toContain("eslint . --max-warnings 0")
    expect(steps.indexOf("eslint . --max-warnings 0")).toBeLessThan(steps.findIndex((s) => s.startsWith("vite build")))
  })
})
