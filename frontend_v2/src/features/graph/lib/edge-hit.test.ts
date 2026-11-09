import { describe, expect, it } from "vitest"
import { linkEndKey, nearestLink } from "./edge-hit"

const node = (key: string, x: number, y: number) => ({ key, x, y })

describe("nearestLink", () => {
  const links = [
    { source: node("a", 0, 0), target: node("b", 10, 0), type: "OWNS" },
    { source: node("a", 0, 0), target: node("c", 0, 10), type: "PAID" },
  ]

  it("finds the edge under the pointer and gives its two ends", () => {
    const hit = nearestLink(links, 5, 0.5, 2)
    expect(hit?.type).toBe("OWNS")
    expect([linkEndKey(hit!.source), linkEndKey(hit!.target)]).toEqual(["a", "b"])
  })

  it("picks the nearer of two edges", () => {
    expect(nearestLink(links, 0.4, 6, 2)?.type).toBe("PAID")
  })

  it("finds nothing off every edge or past an end", () => {
    expect(nearestLink(links, 5, 5, 2)).toBeNull()
    expect(nearestLink(links, 14, 0, 2)).toBeNull()
  })

  it("skips edges not yet placed", () => {
    expect(nearestLink([{ source: "a", target: "b", type: "OWNS" }], 0, 0, 5)).toBeNull()
  })
})
