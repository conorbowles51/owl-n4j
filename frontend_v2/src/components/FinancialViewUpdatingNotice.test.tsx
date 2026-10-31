import { act, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { clearUpdatingViews, noteViewAnswer } from "@/lib/financial-view-updates"
import { FinancialViewUpdatingNotice, UPDATING_POLL_MS } from "./FinancialViewUpdatingNotice"

beforeEach(() => {
  clearUpdatingViews()
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  clearUpdatingViews()
})

function show(client = new QueryClient()) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/cases/c1/financial"]}>
        <Routes>
          <Route path="/cases/:id/*" element={<FinancialViewUpdatingNotice />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

it("shows nothing while every answer is current", () => {
  show()
  expect(screen.queryByTestId("financial-view-updating")).toBeNull()
})

it("keeps saying so until the page has fetched the view again, then clears", async () => {
  const client = new QueryClient()
  let finishRefetch!: () => void
  const refetch = vi.spyOn(client, "refetchQueries").mockImplementation(
    () => new Promise<void>((resolve) => (finishRefetch = resolve))
  )
  const remove = vi.spyOn(client, "removeQueries")
  const endpoint = "/api/financial/ledger-summary?case_id=c1"
  act(() => noteViewAnswer(endpoint, "2026-10-31T07:15:00+00:00"))
  noteViewAnswer("/api/financial/ledger-summary?case_id=other-case", "2026-10-31T07:15:00+00:00")
  const fetch = vi.fn().mockResolvedValue(new Response('{"total":12}', { status: 200 }))
  vi.stubGlobal("fetch", fetch)
  show(client)
  expect(screen.getByTestId("financial-view-updating").textContent).toMatch(
    /Updating after a recent change\. Some figures on this page are from .+ and are being recomputed/
  )
  await act(async () => {
    await vi.advanceTimersByTimeAsync(UPDATING_POLL_MS + 10)
  })
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(fetch.mock.calls[0][0]).toBe(endpoint)
  expect(remove).toHaveBeenCalledWith({ type: "inactive" })
  expect(refetch).toHaveBeenCalledWith({ type: "active" })
  // The view answered current, but the page still shows its previous copy until its refetch lands.
  expect(screen.getByTestId("financial-view-updating")).toBeTruthy()
  await act(async () => {
    finishRefetch()
    await vi.advanceTimersByTimeAsync(0)
  })
  expect(screen.queryByTestId("financial-view-updating")).toBeNull()
})

it("keeps saying so while the view still answers updating", async () => {
  const client = new QueryClient()
  const refetch = vi.spyOn(client, "refetchQueries")
  const endpoint = "/api/financial/ledger-summary?case_id=c1"
  act(() => noteViewAnswer(endpoint, "2026-10-31T07:15:00+00:00"))
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response("{}", {
          status: 200,
          headers: { "X-Financial-View-State": "updating", "X-Financial-View-As-Of": "2026-10-31T07:16:00+00:00" },
        })
      )
    )
  )
  show(client)
  await act(async () => {
    await vi.advanceTimersByTimeAsync(UPDATING_POLL_MS + 10)
  })
  expect(refetch).not.toHaveBeenCalled()
  expect(screen.getByTestId("financial-view-updating")).toBeTruthy()
})
