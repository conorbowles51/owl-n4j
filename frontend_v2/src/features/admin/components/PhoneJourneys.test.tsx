import { describe, expect, it } from "vitest"
import { JOURNEY_WORDS, funnelLine } from "./phone-journey-words"
import FIELDS from "@/lib/ux-event-fields.json"

describe("phone journeys on the Speed page", () => {
  it("names every journey the events can carry", () => {
    expect(Object.keys(JOURNEY_WORDS)).toEqual(FIELDS.field_types.journey.enum)
  })
  it("states the steps reached", () => {
    expect(funnelLine({ journey: "J-3", started: 2, completed: 1, abandoned: 1, median_ms: 1, steps: [{ step: 1, reached: 2 }, { step: 2, reached: 1 }] }))
      .toBe("step 1: 2 · step 2: 1")
  })
})
