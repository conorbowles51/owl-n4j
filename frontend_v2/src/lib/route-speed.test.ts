import { describe, expect, it } from "vitest"
import { routePage } from "./route-speed"
import { noteForTest, resetBrowserTiming, routeShape, viewDetail } from "./browser-timing"

const CASE = "d5b330d1-1111-2222-3333-444455556666"

describe("route page names", () => {
  it("names every case, admin and app route, and nothing raw", () => {
    expect(routePage(`/cases/${CASE}/timeline`)).toEqual({ page: "case/timeline", caseId: CASE })
    expect(routePage(`/cases/${CASE}/graph/`)).toEqual({ page: "case/graph", caseId: CASE })
    expect(routePage(`/cases/${CASE}`)).toEqual({ page: "case/workspace", caseId: CASE })
    expect(routePage(`/cases/${CASE}/profiles`)).toEqual({ page: "case/dossiers", caseId: CASE })
    expect(routePage(`/cases/${CASE}/secret-thing`)).toEqual({ page: "other", caseId: CASE })
    expect(routePage("/")).toEqual({ page: "cases", caseId: null })
    expect(routePage("/cases")).toEqual({ page: "cases", caseId: null })
    expect(routePage("/admin")).toEqual({ page: "admin", caseId: null })
    expect(routePage("/admin/speed")).toEqual({ page: "admin/speed", caseId: null })
    expect(routePage("/admin/usage")).toEqual({ page: "admin/ai-costs", caseId: null })
    expect(routePage("/settings/ai")).toEqual({ page: "settings/ai", caseId: null })
    expect(routePage("/login")).toEqual({ page: null, caseId: null })
    expect(routePage("/what/ever")).toEqual({ page: "other", caseId: null })
  })
})

describe("browser figures", () => {
  it("reduces a request to its route shape, same origin only", () => {
    const origin = window.location.origin
    expect(routeShape(`${origin}/api/evidence/${CASE}/page/3?width=1200`)).toBe("/api/evidence/{id}/page/{id}")
    expect(routeShape(`${origin}/api/files/statement%20march.pdf`)).toBe("/api/files/{file}")
    expect(routeShape(`${origin}/assets/index-Bx12.js`)).toBe("/assets/index-Bx12.js")
    expect(routeShape("http://elsewhere.example/api/x")).toBeNull()
  })

  it("adds up the resources and long tasks inside the view only", () => {
    resetBrowserTiming()
    const origin = window.location.origin
    noteForTest("resource", { name: `${origin}/api/timeline`, startTime: 100, requestStart: 900, responseStart: 1000, responseEnd: 5000, duration: 4900, transferSize: 2000 })
    noteForTest("resource", { name: `${origin}/api/significant/${CASE}`, startTime: 120, requestStart: 130, responseStart: 140, responseEnd: 160, duration: 40, transferSize: 300 })
    noteForTest("resource", { name: `${origin}/api/later`, startTime: 9000, requestStart: 9001, responseStart: 9002, responseEnd: 9003, duration: 3, transferSize: 5 })
    noteForTest("resource", { name: "http://cdn.example/x.js", startTime: 150, requestStart: 0, responseStart: 0, responseEnd: 400, duration: 250, transferSize: 0 })
    noteForTest("longtask", { start: 200, duration: 180 })
    noteForTest("longtask", { start: 9500, duration: 900 })
    const detail = viewDetail(100, 6000, false)
    expect(detail.resources).toBe(3)
    expect(detail.resource_bytes).toBe(2300)
    expect(detail.queue_max_ms).toBe(800)
    expect(detail.queue_total_ms).toBe(810)
    expect(detail.transfer_total_ms).toBe(4020)
    expect(detail.largest_ms).toBe(4900)
    expect(detail.largest_route).toBe("/api/timeline")
    expect(detail.largest_bytes).toBe(2000)
    expect(detail.nav_response_ms).toBeUndefined()
    resetBrowserTiming()
  })
})

describe("one opening, seen by every timer", () => {
  it("gives the route timer and the Financial timer each their own LOAD", async () => {
    const { takeDocumentLoad } = await import("@/features/financial/lib/page-speed")
    const original = performance.getEntriesByType
    performance.getEntriesByType = ((type: string) =>
      type === "navigation" ? [{ name: window.location.href }] : []) as typeof performance.getEntriesByType
    try {
      expect(takeDocumentLoad(window.location.pathname, "route")).toBe(true)
      expect(takeDocumentLoad(window.location.pathname, "route")).toBe(false)
      expect(takeDocumentLoad(window.location.pathname, "financial")).toBe(true)
    } finally {
      performance.getEntriesByType = original
    }
  })
})
