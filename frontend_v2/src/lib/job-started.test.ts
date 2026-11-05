import { describe, expect, it } from "vitest"
import { startsJob } from "./job-started"

describe("startsJob", () => {
  it("names the requests that start a long phone job", () => {
    for (const url of ["/api/phones/exports", "/api/phones/media/derive-batches", "/api/phones/media/image-index", "/api/phones/reparse", "/api/phone-analysis/runs", "/api/pattern/c1/together", "/api/evidence/process", "/api/phones/e1/clock-offset", "/api/phones/readings/r1/confirm"]) {
      expect(startsJob(url, "POST")).toBe(true)
    }
  })
  it("ignores reads and other writes", () => {
    expect(startsJob("/api/phones/exports", "GET")).toBe(false)
    expect(startsJob("/api/phones/exports/describe", "POST")).toBe(false)
    expect(startsJob("/api/phones/media/derive-batches/describe", "POST")).toBe(false)
    expect(startsJob("/api/phones/settings", "POST")).toBe(false)
    expect(startsJob("/api/phones/readings/r1/correct/preview", "POST")).toBe(false)
  })
})
