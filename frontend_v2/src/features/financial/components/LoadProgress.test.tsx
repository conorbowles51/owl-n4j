import { act, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { answerRequest, endRequest, receiveBytes, resetRequestsForTest, startRequest } from "@/lib/request-progress"
import { LoadProgress } from "./LoadProgress"
import { picture } from "../lib/load-progress"

beforeEach(() => {
  resetRequestsForTest()
  localStorage.clear()
  vi.useFakeTimers({ toFake: ["setTimeout", "setInterval", "performance", "requestAnimationFrame", "cancelAnimationFrame"] })
})
afterEach(() => vi.useRealTimers())

function mount(client = new QueryClient()) {
  // A query that never settles keeps the page "loading", as a slow view does.
  void client.prefetchQuery({ queryKey: ["slow"], queryFn: () => new Promise(() => undefined) })
  return render(
    <QueryClientProvider client={client}>
      <LoadProgress caseId="case-1" page="financial/ledger" />
    </QueryClientProvider>
  )
}

it("counts parts and bytes from the reads, never reaching 100% before the data is shown", () => {
  const reads = [
    { id: 1, endpoint: "/api/financial/ledger", what: "payments", started: 0, answered: 10, received: 3 * 1024 * 1024, total: 6 * 1024 * 1024, ended: null, failed: null },
    { id: 2, endpoint: "/api/financial/ledger-accounts", what: "accounts", started: 0, answered: 5, received: 100, total: 100, ended: 8, failed: null },
  ]
  const view = picture(reads)
  expect(view.step).toBe("Receiving payments")
  expect(view.partsDone).toBe(1)
  expect(view.partsAsked).toBe(2)
  expect(view.done).toBeCloseTo(1.5)
  expect(view.total).toBe(3)
  expect(picture([{ ...reads[0], ended: 20, received: reads[0].total }]).step).toBe("Drawing the page")
})

it("says what is loading with true counts, says when it has not moved, and offers a retry past 10 s", () => {
  mount()
  const id = startRequest("/api/financial/ledger?case_id=case-1")
  act(() => vi.advanceTimersByTime(600))
  expect(screen.getByRole("status").textContent).toMatch(/Working out payments on the server/)
  expect(screen.getByRole("status").textContent).toMatch(/0 of 1 part loaded · 0%/)
  act(() => {
    answerRequest(id, 4 * 1024 * 1024)
    receiveBytes(id, 1024 * 1024)
  })
  act(() => vi.advanceTimersByTime(500))
  expect(screen.getByRole("status").textContent).toMatch(/Receiving payments…1\.0 MB of 4\.0 MB/)
  expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("12")
  act(() => vi.advanceTimersByTime(3500))
  expect(screen.getByRole("status").textContent).toMatch(/Still receiving payments — no change for \d+ s/)
  expect(screen.queryByText("Try again")).toBeNull()
  act(() => vi.advanceTimersByTime(6500))
  expect(screen.getByText(/Receiving payments has taken \d+ s\. You can keep waiting or try again\./)).toBeTruthy()
  expect(screen.getByText("Try again")).toBeTruthy()
  // Bytes received never move the bar backwards when a new part starts.
  act(() => {
    startRequest("/api/financial/ledger-accounts?case_id=case-1")
  })
  act(() => vi.advanceTimersByTime(500))
  expect(Number(screen.getByRole("progressbar").getAttribute("aria-valuenow"))).toBeGreaterThanOrEqual(12)
})

it("names the part that failed and offers to try again, never a bare spinner", () => {
  mount()
  const id = startRequest("/api/financial/ledger-accounts?case_id=case-1")
  act(() => endRequest(id, "Server error"))
  act(() => vi.advanceTimersByTime(500))
  expect(screen.getByRole("alert").textContent).toMatch(/Loading accounts failed: Server error\./)
  expect(screen.getByText("Try again")).toBeTruthy()
})

it("estimates time left from this page's last load on this case, worded as an estimate", () => {
  localStorage.setItem("loupe:view-load-ms:case-1:financial/ledger", "8000")
  mount()
  startRequest("/api/financial/ledger-first-view?case_id=case-1")
  act(() => vi.advanceTimersByTime(2000))
  expect(screen.getByRole("status").textContent).toMatch(/about 6 s left \(this page took 8 s last time\)/)
})
