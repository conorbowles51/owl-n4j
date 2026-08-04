import { describe, expect, it } from "vitest"
import { progressFromRect, segment } from "./useScrollProgress"

describe("progressFromRect", () => {
  const viewport = 800

  it("is 0 before the section has begun scrolling", () => {
    expect(progressFromRect({ top: 0, height: 2400 }, viewport)).toBe(0)
  })

  it("is 1 once the section has fully scrolled past", () => {
    expect(progressFromRect({ top: -1600, height: 2400 }, viewport)).toBe(1)
  })

  it("is 0.5 at the midpoint of the scrollable distance", () => {
    expect(progressFromRect({ top: -800, height: 2400 }, viewport)).toBe(0.5)
  })

  it("clamps above 1 when scrolled well past", () => {
    expect(progressFromRect({ top: -9000, height: 2400 }, viewport)).toBe(1)
  })

  it("clamps below 0 when the section is still below the fold", () => {
    expect(progressFromRect({ top: 5000, height: 2400 }, viewport)).toBe(0)
  })

  it("returns 0 for a section shorter than the viewport", () => {
    expect(progressFromRect({ top: -100, height: 400 }, viewport)).toBe(0)
  })
})

describe("segment", () => {
  it("is 0 before the segment starts", () => {
    expect(segment(0.1, 0.3, 0.6)).toBe(0)
  })

  it("is 1 after the segment ends", () => {
    expect(segment(0.9, 0.3, 0.6)).toBe(1)
  })

  it("runs 0..1 across the segment", () => {
    expect(segment(0.3, 0.3, 0.6)).toBe(0)
    expect(segment(0.45, 0.3, 0.6)).toBeCloseTo(0.5)
    expect(segment(0.6, 0.3, 0.6)).toBe(1)
  })

  it("treats a zero-width segment as a switch", () => {
    expect(segment(0.4, 0.5, 0.5)).toBe(0)
    expect(segment(0.5, 0.5, 0.5)).toBe(1)
  })
})
