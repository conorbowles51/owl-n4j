import { describe, expect, it } from "vitest"
import { EVERY_PHONE, mediaFilter, NONE } from "./media-queries"

describe("mediaFilter", () => {
  it("stays the start-up prefetch's filter when no extra filter is set, so the page reuses that cache entry", () => {
    expect(mediaFilter("c", "e", null, "", "", {})).toEqual(mediaFilter("c", "e", null, "", ""))
    expect(mediaFilter("c", "e", "t", "", "")).toEqual({ case_id: "c", phones: ["e"], thread_key: "t" })
  })
  it("leaves the phones out for every phone in the case and carries the app, person and dates that are set", () => {
    expect(mediaFilter("c", EVERY_PHONE, null, NONE, "", { apps: ["WhatsApp"], to_instant: "2026-01-02T00:00:00Z" }))
      .toEqual({ case_id: "c", categories: [""], apps: ["WhatsApp"], to_instant: "2026-01-02T00:00:00Z" })
  })
})
