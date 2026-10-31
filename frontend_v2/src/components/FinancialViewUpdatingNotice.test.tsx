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

it("says the figures are a previous copy being recomputed, then refetches and clears when the view is current", async () => {
  const client = new QueryClient()
  const invalidate = vi.spyOn(client, "invalidateQueries")
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
  expect(invalidate).toHaveBeenCalledWith({ refetchType: "active" })
  expect(screen.queryByTestId("financial-view-updating")).toBeNull()
})
