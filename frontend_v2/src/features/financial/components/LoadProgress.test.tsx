import { act, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { answerRequest, endRequest, receiveBytes, resetRequestsForTest, startRequest, unpackProgress } from "@/lib/request-progress"
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

it("after the data is shown, names a part that failed until it is asked again and loads", async () => {
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <LoadProgress caseId="case-1" page="financial/ledger" />
    </QueryClientProvider>
  )
  const failed = startRequest("/api/financial/ledger-accounts?case_id=case-1")
  act(() => endRequest(failed, "Server error"))
  // Nothing is fetching in the query cache: the page settles at the next frame.
  await act(async () => {
    await vi.advanceTimersByTimeAsync(600)
  })
  expect(screen.getByTestId("load-progress-failed").textContent).toMatch(/Loading accounts failed: Server error\./)
  let again = 0
  act(() => {
    again = startRequest("/api/financial/ledger-accounts?case_id=case-1")
  })
  expect(screen.queryByTestId("load-progress-failed")).toBeNull() // being asked again: no stale failure
  act(() => endRequest(again, null))
  expect(screen.queryByTestId("load-progress-failed")).toBeNull()
  expect(screen.queryByTestId("load-progress")).toBeNull()
})

it("says the answer is being unpacked, with rows of rows, once its bytes are in, and counts that as movement", () => {
  mount()
  const id = startRequest("/api/financial/ledger?case_id=case-1")
  act(() => {
    answerRequest(id, 2 * 1024 * 1024)
    receiveBytes(id, 2 * 1024 * 1024)
    unpackProgress(id, 4000, 27926, "rows")
  })
  act(() => vi.advanceTimersByTime(600))
  expect(screen.getByRole("status").textContent).toMatch(/Unpacking payments…2\.0 MB of 2\.0 MB4,000 of 27,926 rows unpacked/)
  // Rows moving every second keep it from saying "Still …".
  for (let step = 1; step <= 5; step += 1) {
    act(() => unpackProgress(id, 4000 + step * 4000, 27926, "rows"))
    act(() => vi.advanceTimersByTime(1000))
  }
  expect(screen.getByRole("status").textContent).not.toMatch(/Still/)
  expect(screen.getByRole("status").textContent).toMatch(/24,000 of 27,926 rows unpacked/)
})

it("estimates time left while unpacking only from the measured rate of rows, never from bytes already in", () => {
  mount()
  const id = startRequest("/api/financial/ledger?case_id=case-1")
  act(() => {
    answerRequest(id, 2 * 1024 * 1024)
    receiveBytes(id, 2 * 1024 * 1024)
    unpackProgress(id, 1000, 2000, "characters")
  })
  act(() => vi.advanceTimersByTime(600))
  expect(screen.getByRole("status").textContent).toMatch(/finding the rows: 50% looked through/)
  expect(screen.getByRole("status").textContent).not.toMatch(/left/)
  act(() => unpackProgress(id, 0, 20000, "rows"))
  act(() => vi.advanceTimersByTime(2000))
  act(() => unpackProgress(id, 5000, 20000, "rows"))
  act(() => vi.advanceTimersByTime(500))
  // At the redraw 2.5 s after rows started, 5,000 done: 15,000 left at that rate is 7.5 s, shown as about 8 s.
  expect(screen.getByRole("status").textContent).toMatch(/5,000 of 20,000 rows unpacked/)
  expect(screen.getByRole("status").textContent).toMatch(/about 8 s left for this part/)
})
