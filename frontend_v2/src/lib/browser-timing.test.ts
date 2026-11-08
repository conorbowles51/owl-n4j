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

  it("the shared checks are not the page asking for data", () => {
    expect(isAppStartCheck("/api/auth/me")).toBe(true)
    expect(isAppStartCheck("/api/request-speed/page-views")).toBe(true)
    expect(isAppStartCheck("/api/evidence-folders/tree")).toBe(false)
  })

  it("names the document's first data request, skipping scripts and the shared checks", () => {
    noteForTest("resource", resource("/assets/index-abc.js", 50))
    noteForTest("resource", resource("/api/auth/me", 100))
    noteForTest("resource", resource("/api/request-speed/page-views", 150))
    noteForTest("resource", resource(`/api/cases/${CASE}/evidence`, 7200))
    noteForTest("resource", resource("/api/financial/categories", 7900))
    expect(firstDataRequest()?.startTime).toBe(7200)
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
