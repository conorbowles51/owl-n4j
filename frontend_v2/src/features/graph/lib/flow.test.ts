import { describe, expect, it } from "vitest"
import { arrowWidth, flowAnchors, flowWords } from "./flow"
import { pathResultWords } from "./path-words"

describe("flow view", () => {
  it("opens on the person with the most contacts", () => {
    const pairs = [{ a: "x", b: "y", aName: "X", bName: "Y" }, { a: "x", b: "z", aName: "X", bName: "Z" }]
    expect(flowAnchors(pairs)[0]).toEqual({ key: "x", name: "X", pairs: 2 })
  })
  it("says each direction in true counts", () => {
    expect(flowWords(120, 1, 0)).toEqual({ total: 121, words: "120 messages, 1 call" })
    expect(flowWords(0, 0, 0)).toEqual({ total: 0, words: "none" })
  })
  it("draws more volume thicker, within bounds", () => {
    expect(arrowWidth(100)).toBeGreaterThan(arrowWidth(10))
    expect(arrowWidth(1_000_000)).toBe(10)
  })
})

describe("Shortest Paths words", () => {
  it("states pairs with no path inside the hop limit", () => {
    expect(pathResultWords([{ length: 3 }, { length: 5 }], 3, 10)).toBe("Found a path for 2 of 3 pairs; the longest is 5 hops; 1 had no path within 10 hops. Shown in spotlight.")
    expect(pathResultWords([{ length: 1 }], 1, 10)).toBe("Found a path for 1 of 1 pair; the longest is 1 hop. Shown in spotlight.")
  })
})
