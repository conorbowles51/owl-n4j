import { describe, expect, it } from "vitest"
import { readWholeResult } from "./select-all"

const fake = (n: number, cut?: number) => async (offset: number, limit: number) => ({
  file_total: n,
  files: Array.from({ length: Math.max(0, Math.min(limit, (cut ?? n) - offset)) }, (_, i) => ({ id: `f${offset + i}` })),
})

describe("select all after a filter", () => {
  it("returns the whole result, not the page", async () => {
    const out = await readWholeResult(fake(1203))
    expect(out.files).toHaveLength(1203)
    expect(out.total).toBe(1203)
    expect(out.complete).toBe(true)
  })
  it("says so when the server stopped early", async () => {
    const out = await readWholeResult(fake(1000, 500))
    expect(out.files).toHaveLength(500)
    expect(out.complete).toBe(false)
  })
  it("reads an empty result", async () => {
    expect((await readWholeResult(fake(0))).files).toEqual([])
  })
})
