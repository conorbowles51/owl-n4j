import { afterEach, describe, expect, it, vi } from "vitest"

import { countSentence, fmt } from "./count-sentence"

afterEach(() => vi.restoreAllMocks())

describe("fmt", () => {
  it("gives the en-US text of toLocaleString without building a formatter per call (lx-mainthread: 208 ms on P12)", () => {
    const perCall = vi.spyOn(Number.prototype, "toLocaleString")
    const samples = [0, 1, 7, 999, 1000, 12345, 1234567.891, -4200, 0.5, 1e21]
    const got = samples.map(fmt)
    expect(perCall).not.toHaveBeenCalled()
    perCall.mockRestore()
    expect(got).toEqual(samples.map((n) => n.toLocaleString("en-US")))
    expect(countSentence({ shown: 1200, total: 34567, noun: "messages" })).toBe("Showing 1,200 of 34,567 messages")
  })
})
