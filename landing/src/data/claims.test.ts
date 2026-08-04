import { readFileSync, readdirSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { retired } from "./claims"

/**
 * claims.ts and the test files quote the retired phrases by definition, so they are
 * excluded. Without this the suite can never pass.
 */
const EXCLUDED = /(\.test\.tsx?|[\\/]claims\.ts)$/

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) return sourceFiles(full)
    return /\.(tsx?|css|html)$/.test(entry.name) && !EXCLUDED.test(full) ? [full] : []
  })
}

describe("retired claims", () => {
  const files = sourceFiles("src")

  it.each(retired)("%s appears nowhere in src/", (phrase) => {
    const offenders = files.filter((f) => readFileSync(f, "utf8").includes(phrase))
    expect(offenders).toEqual([])
  })
})
