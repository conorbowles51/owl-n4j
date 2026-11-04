import { describe, expect, it } from "vitest"
import { noTimeWords } from "./no-time-words"

describe("the Media grid's no-time sentence", () => {
  it("never says a file carried by an undated message was carried by no message", () => {
    expect(noTimeWords(1, 0)).toBe(" 1 was carried only by messages with no time; it has no time and is listed at the end.")
    expect(noTimeWords(3, 1)).toBe(" 1 was carried by no message and 2 were carried only by messages with no time; they have no time and are listed at the end.")
    expect(noTimeWords(2, 2)).toBe(" 2 were carried by no message; they have no time and are listed at the end.")
    expect(noTimeWords(0, 0)).toBe("")
    expect(noTimeWords(4, undefined)).toBe(" 4 have no time; they are listed at the end.")
  })
})
