import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AppStartWaiting, GAP_SHOW_MS, GIVE_UP_MS } from "./app-start-waiting"
import { resetRequestsForTest, startRequest } from "@/lib/request-progress"

let chunkPending = false
vi.mock("@/lib/page-chunks", () => ({ pageChunksPending: () => chunkPending }))

let nowMs = 0
const PAINT_AT = 100

function tick(toMs: number) {
  nowMs = toMs
  act(() => {
    vi.advanceTimersByTime(1000)
  })
}

describe("the shell tells the waiter when a painted page has asked for nothing", () => {
  beforeEach(() => {
    resetRequestsForTest()
    chunkPending = false
    nowMs = 0
    vi.useFakeTimers()
    vi.spyOn(performance, "now").mockImplementation(() => nowMs)
    vi.spyOn(performance, "getEntriesByType").mockImplementation(((type: string) =>
      type === "paint" ? [{ name: "first-contentful-paint", startTime: PAINT_AT } as PerformanceEntry] : []) as never)
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it("shows the shared waiting panel once the gap passes 2 s, and hides it when the first data request leaves", () => {
    render(<AppStartWaiting />)
    expect(screen.queryByTestId("progress-panel")).toBeNull()
    tick(PAINT_AT + GAP_SHOW_MS - 500)
    expect(screen.queryByTestId("progress-panel")).toBeNull()
    tick(PAINT_AT + GAP_SHOW_MS + 500)
    expect(screen.getByTestId("progress-panel")).toBeTruthy()
    expect(screen.getByRole("status").textContent).toContain("Opening the page")
    // The sign-in check, the speed beacons and the sidebar's own queries are not the page asking for data.
    act(() => {
      startRequest("/api/auth/me")
      startRequest("/api/request-speed/page-views")
      startRequest("/api/significant/cded78d0-e659-44cc-940d-d8f8c8012760")
      startRequest("/api/phones?case_id=cded78d0-e659-44cc-940d-d8f8c8012760")
      startRequest("/api/phones/my-marks")
    })
    expect(screen.getByTestId("progress-panel")).toBeTruthy()
    act(() => {
      startRequest("/api/evidence-folders/tree")
    })
    expect(screen.queryByTestId("progress-panel")).toBeNull()
    // One-shot: it never comes back for this document.
    tick(PAINT_AT + GAP_SHOW_MS + 9000)
    expect(screen.queryByTestId("progress-panel")).toBeNull()
  })

  it("never doubles the route's own loading panel while the page's code is on its way", () => {
    chunkPending = true
    render(<AppStartWaiting />)
    tick(PAINT_AT + GAP_SHOW_MS + 500)
    expect(screen.queryByTestId("progress-panel")).toBeNull()
    chunkPending = false
    tick(PAINT_AT + GAP_SHOW_MS + 1500)
    expect(screen.getByTestId("progress-panel")).toBeTruthy()
  })

  it("a document whose page asked for data before the gap never shows it", () => {
    act(() => {
      startRequest("/api/cases")
    })
    render(<AppStartWaiting />)
    tick(PAINT_AT + GAP_SHOW_MS + 500)
    expect(screen.queryByTestId("progress-panel")).toBeNull()
  })

  it("after an in-document sign-in the gap runs from the shell appearing, not the login screen's paint", () => {
    nowMs = 30000 // the person typed credentials for 30 s; the document painted at PAINT_AT
    render(<AppStartWaiting />)
    tick(30500)
    expect(screen.queryByTestId("progress-panel")).toBeNull()
    tick(30000 + GAP_SHOW_MS + 500)
    expect(screen.getByTestId("progress-panel")).toBeTruthy()
  })

  it("stops watching after a minute rather than stay up on a page that never reads", () => {
    render(<AppStartWaiting />)
    tick(PAINT_AT + GAP_SHOW_MS + 500)
    expect(screen.getByTestId("progress-panel")).toBeTruthy()
    tick(PAINT_AT + GIVE_UP_MS + 1500)
    expect(screen.queryByTestId("progress-panel")).toBeNull()
  })
})
