import { describe, expect, it } from "vitest"
import { phoneQueryTarget } from "./phone-query"

describe("phone addresses from links (07 4.13, lx-collect)", () => {
  it("opens a thread, a record or a person in Conversations", () => {
    expect(phoneQueryTarget("c1", "?thread=wa%3A1")).toBe("/cases/c1/conversations?thread=wa%3A1")
    expect(phoneQueryTarget("c1", "?record=r1")).toBe("/cases/c1/conversations?record=r1")
    expect(phoneQueryTarget("c1", "?identity=phone%3A%2B1")).toBe("/cases/c1/conversations?tab=people&people=phone%3A%2B1")
  })
  it("leaves the phone list in place for anything else", () => {
    expect(phoneQueryTarget("c1", "")).toBeNull()
    expect(phoneQueryTarget("c1", "?file=f1")).toBeNull()
  })
})
