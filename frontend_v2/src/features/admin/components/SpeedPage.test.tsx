import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { formatDuration, type SpeedSummary } from "../speed"
import { SpeedPage } from "./SpeedPage"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))

const summary: SpeedSummary = {
  days: 1,
  routes: [
    { kind: "api", method: "GET", route: "/api/financial/summary", count: 1200, p50_ms: 850, p95_ms: 9800,
      max_ms: 14200, mean_ms: 1500, bytes: 5 * 1024 * 1024, errors: 3, cases: 2 },
    { kind: "page", method: "LOAD", route: "financial/overview", count: 4, p50_ms: 2100, p95_ms: 3000,
      max_ms: 3100, mean_ms: 2200, bytes: 0, errors: 0, cases: 1 },
  ],
  slow: [
    { at: "2026-10-28T13:00:00Z", kind: "api", method: "GET", route: "/api/financial/summary",
      case_id: "d5b330d1-1111-2222-3333-444455556666", case_title: "Merrick", status: 200,
      duration_ms: 9800, bytes: 100, user_name: "Alex", started_at: "2026-10-28T12:59:50.200Z", pid: 1234,
      pg_ms: 6731, cache: "miss", loop_lag_max_ms: 1941, host_cpu_pressure: 69.1, fleet_cores: 1.34 },
    { at: "2026-10-28T12:00:00Z", kind: "api", method: "GET", route: "/api/timeline",
      case_id: null, case_title: null, status: 200, duration_ms: 4000, bytes: 10, user_name: "Before" },
  ],
  cases: [{ id: "d5b330d1-1111-2222-3333-444455556666", title: "Merrick", count: 1200 }],
  slow_row_seconds: 2,
  slow_keep_days: 30,
}
let client: QueryClient
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(fetchAPI).mockResolvedValue(summary)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})
afterEach(() => {
  cleanup()
  client.clear()
})

describe("SpeedPage", () => {
  it("shows each route slowest first with plain-word columns, and the slow requests", async () => {
    render(
      <QueryClientProvider client={client}>
        <SpeedPage />
      </QueryClientProvider>
    )
    const row = (await screen.findAllByText("GET /api/financial/summary"))[0].closest("tr")!
    expect(within(row).getByText("850 ms")).toBeTruthy()
    expect(within(row).getByText("9.8 s")).toBeTruthy()
    expect(within(row).getByText("14.2 s")).toBeTruthy()
    expect(within(row).getByText("1,200")).toBeTruthy()
    expect(within(row).getByText("5.0 MB")).toBeTruthy()
    expect(screen.getByText("Opened financial/overview")).toBeTruthy()
    expect(screen.getByText("Typical")).toBeTruthy()
    expect(screen.getByText("Slow end")).toBeTruthy()
    expect(screen.getByText(/Slow requests \(over 2 s, kept 30 days\)/)).toBeTruthy()
    const slow = screen.getByText("Alex").closest("tr")!
    expect(within(slow).getByText("Merrick")).toBeTruthy()
    expect(within(slow).getByText("ok")).toBeTruthy()
    // Its minute: database time (computed, not a kept copy), how long its worker was held, machine and jobs load.
    expect(within(slow).getByText("6.7 s (computed)")).toBeTruthy()
    expect(within(slow).getByText("1.9 s")).toBeTruthy()
    expect(within(slow).getByText("69%")).toBeTruthy()
    expect(within(slow).getByText("1.3")).toBeTruthy()
    // A row from before these figures were recorded shows blanks, never zero.
    const older = screen.getByText("Before").closest("tr")!
    expect(within(older).queryByText(/%|computed|0 ms/)).toBeNull()
    expect(vi.mocked(fetchAPI)).toHaveBeenCalledWith("/api/request-speed/summary?days=1")
  })

  it("formats durations in plain units", () => {
    expect(formatDuration(null)).toBe("–")
    expect(formatDuration(12.4)).toBe("12 ms")
    expect(formatDuration(2500)).toBe("2.5 s")
    expect(formatDuration(125000)).toBe("2 min 5 s")
  })
})
