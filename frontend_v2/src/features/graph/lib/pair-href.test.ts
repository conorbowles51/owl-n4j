import { describe, expect, it } from "vitest"
import { pairConversationsHref } from "./pair-href"

describe("pairConversationsHref", () => {
  it("opens Conversations, Between A and B, for the pair", () => {
    const href = pairConversationsHref("case 1", "phone-identity:a", "phone-identity:b")
    const [path, query] = href.split("?")
    expect(path).toBe("/cases/case%201/conversations")
    const q = new URLSearchParams(query)
    expect(q.get("tab")).toBe("people")
    expect(q.get("people")).toBe("phone-identity:a,phone-identity:b")
    expect(q.get("mode")).toBe("between")
  })
})
