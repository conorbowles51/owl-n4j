import { describe, expect, it } from "vitest"
import { undatedWords } from "./stream-words"

const noun = { one: "message", many: "messages" }

describe("the undated group's header (03 C-3, 07 J-4)", () => {
  it("names the group, counts it and says where it is", () => {
    expect(undatedWords(6, noun, "last")).toBe("No time recorded. 6 messages have no time and are listed at the end.")
    expect(undatedWords(1, noun, "first")).toBe("No time recorded. 1 message has no time and is listed at the start.")
    expect(undatedWords(12345, noun, "last")).toContain("12,345 messages have")
  })
})
