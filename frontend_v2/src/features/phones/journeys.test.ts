import { describe, expect, it } from "vitest"
import { ALL } from "../../../journeys/specs/index.mjs"

// 07 section 11: which job's gate carries each journey.
const GATES: Record<string, string[]> = {
  "cb-capture": ["J-1a"],
  "cb-interpret": ["J-8a"],
  "cb-screens": ["J-1b", "J-2", "J-3a", "J-4", "J-6", "J-7", "J-8b", "J-10a", "J-11", "J-12", "J-13", "J-13b", "J-14a", "J-15", "J-16", "J-17"],
  "cb-pol": ["J-5a", "J-9", "J-10b"],
  "cb-crossev": ["J-3b", "J-5b"],
  "cb-approaches": ["J-5c", "J-14b"],
}

describe("journey tests are handed to their owners", () => {
  it("every journey in section 11 has a script in its owner's file, and nothing is duplicated", () => {
    const ids = ALL.map((j) => `${j.owner} ${j.id}`)
    expect(new Set(ids).size).toBe(ids.length)
    for (const [owner, journeys] of Object.entries(GATES))
      for (const id of journeys) expect(ids, `${owner} ${id}`).toContain(`${owner} ${id}`)
  })
  it("every journey has a title, a gate and a run function", () => {
    for (const j of ALL) {
      expect(j.title.length, j.id).toBeGreaterThan(5)
      expect(j.gate, j.id).toMatch(/DONE/)
      expect(typeof j.run, j.id).toBe("function")
    }
  })
})
