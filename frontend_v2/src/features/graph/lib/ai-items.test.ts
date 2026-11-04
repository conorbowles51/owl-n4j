import { describe, expect, it } from "vitest"
import { aiItemsLine, orderInsights, summariseAiItems } from "./ai-items"

const insights = [
  { text: "a", rejected: true },
  { text: "b" },
  { text: "c", verified: true, verified_by: "neil" },
  { text: "d" },
]

describe("one consolidated view of an entity's AI facts and insights (FEAT-014)", () => {
  it("counts everything and labels it AI-made", () => {
    const s = summariseAiItems([{ text: "f", pinned: true }, { text: "g" }], insights)
    expect(s).toEqual({ facts: 2, pinnedFacts: 1, insights: 4, personVerified: 1, notReviewed: 2, rejected: 1 })
    expect(aiItemsLine(s)).toBe(
      "AI-made · 2 source-grounded facts (1 pinned) · 4 insights: 1 confirmed by a person, 2 not reviewed, 1 rejected",
    )
  })

  it("orders insights for review without losing any or their stored index", () => {
    const o = orderInsights(insights)
    expect(o.open.map((x) => x.index)).toEqual([1, 3])
    expect(o.confirmed.map((x) => x.index)).toEqual([2])
    expect(o.rejected.map((x) => x.index)).toEqual([0])
    expect(o.open.length + o.confirmed.length + o.rejected.length).toBe(insights.length)
  })
  it("says there are no insights instead of a row of zeros", () => {
    const s = summariseAiItems([{ text: "a" }, { text: "b" }], [])
    expect(aiItemsLine(s)).toBe("AI-made · 2 source-grounded facts · no insights")
  })
})
