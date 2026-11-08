import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { firstDataRequest, isAppStartCheck, noteForTest, resetBrowserTiming, viewDetail } from "./browser-timing"

const CASE = "cded78d0-e659-44cc-940d-d8f8c8012760"

function resource(path: string, startTime: number) {
  return {
    name: window.location.origin + path,
    startTime,
    requestStart: 0,
    responseStart: 0,
    responseEnd: startTime + 1,
    duration: 1,
    transferSize: 10,
  } as Partial<PerformanceResourceTiming>
}

describe("a real person's start on the opening row", () => {
  beforeEach(() => {
    resetBrowserTiming()
    vi.spyOn(performance, "getEntriesByType").mockImplementation(((type: string) =>
      type === "paint" ? [{ name: "first-contentful-paint", startTime: 1240.46 } as PerformanceEntry] : []) as never)
  })
  afterEach(() => vi.restoreAllMocks())

  it("the shell's own requests are not the page asking for data", () => {
    expect(isAppStartCheck("/api/auth/me")).toBe(true)
    expect(isAppStartCheck("/api/request-speed/page-views")).toBe(true)
    // The sidebar's queries leave with the shell on every case page (with or without their query strings).
    expect(isAppStartCheck(`/api/significant/${CASE}`)).toBe(true)
    expect(isAppStartCheck("/api/significant/{id}")).toBe(true)
    expect(isAppStartCheck(`/api/phones?case_id=${CASE}`)).toBe(true)
    expect(isAppStartCheck("/api/phones")).toBe(true)
    expect(isAppStartCheck(`/api/phones/jobs?case_id=${CASE}`)).toBe(true)
    expect(isAppStartCheck("/api/phones/my-marks")).toBe(true)
    // A phone's own pages are the page asking.
    expect(isAppStartCheck("/api/phones/{id}/profile")).toBe(false)
    expect(isAppStartCheck("/api/evidence-folders/tree")).toBe(false)
  })

  it("names the document's first data request, skipping scripts and the shell's own requests", () => {
    noteForTest("resource", resource("/assets/index-abc.js", 50))
    noteForTest("resource", resource("/api/auth/me", 100))
    noteForTest("resource", resource("/api/request-speed/page-views", 150))
    noteForTest("resource", resource(`/api/significant/${CASE}`, 600))
    noteForTest("resource", resource(`/api/phones?case_id=${CASE}`, 900))
    noteForTest("resource", resource(`/api/cases/${CASE}/evidence`, 7200))
    noteForTest("resource", resource("/api/financial/categories", 7900))
    expect(firstDataRequest()?.startTime).toBe(7200)
    expect(firstDataRequest()?.route).toBe("/api/cases/{id}/evidence")
  })

  it("the first data request is kept once seen, so a row written after the buffer trims still has it", () => {
    noteForTest("resource", resource(`/api/cases/${CASE}/evidence`, 7200))
    expect(firstDataRequest()?.startTime).toBe(7200)
    resetBrowserTiming() // clears the kept value too (tests only)
    noteForTest("resource", resource(`/api/cases/${CASE}/evidence`, 5000))
    expect(firstDataRequest()?.startTime).toBe(5000)
    // Later entries never replace the document's first, even after the early entries are trimmed away.
    noteForTest("resource", resource("/api/financial/categories", 100))
    expect(firstDataRequest()?.startTime).toBe(5000)
  })

  it("puts first paint and the first data request on an opening row, never a switch's", () => {
    noteForTest("resource", resource("/api/auth/me", 100))
    noteForTest("resource", resource(`/api/cases/${CASE}/evidence`, 7200))
    const opening = viewDetail(0, 9000, true)
    expect(opening.first_paint_ms).toBe(1240.5)
    expect(opening.first_api_ms).toBe(7200)
    expect(opening.first_api_route).toBe("/api/cases/{id}/evidence")
    const view = viewDetail(0, 9000, false)
    expect(view.first_paint_ms).toBeUndefined()
    expect(view.first_api_ms).toBeUndefined()
    expect(view.first_api_route).toBeUndefined()
  })

  it("a document that never asked for data records no first request", () => {
    noteForTest("resource", resource("/api/auth/me", 100))
    const opening = viewDetail(0, 9000, true)
    expect(opening.first_api_ms).toBeUndefined()
    expect(opening.first_paint_ms).toBe(1240.5)
  })
})
