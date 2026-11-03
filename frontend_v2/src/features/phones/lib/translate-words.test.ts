import { describe, expect, it } from "vitest"
import { translateWords } from "./translate-words"

describe("translateWords", () => {
  it("states what was queued and every message left out, by reason", () => {
    expect(translateWords({ in_conversation: 1240, queued: 1200, left_out: { no_text: 30, already_translated: 9, already_waiting: 1 } })).toBe(
      "1,200 messages of 1,240 queued for translation on this server; nothing is sent anywhere. Left out: 9 already translated, 1 already waiting, 30 with no text.",
    )
  })
  it("says when nothing new was queued", () => {
    expect(translateWords({ in_conversation: 1, queued: 0, left_out: { no_text: 0, already_translated: 1, already_waiting: 0 } })).toBe(
      "Nothing new to translate in this conversation of 1 message. Left out: 1 already translated.",
    )
  })
})
