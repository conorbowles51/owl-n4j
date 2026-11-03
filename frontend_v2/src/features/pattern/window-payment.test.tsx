import { fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

/** 07 J-5 (J-5b, a ledger payment start): a payment has a date and no time, so its window is its whole day. */
const api = vi.hoisted(() => ({
  subjects: vi.fn(), keyDates: vi.fn(), window: vi.fn(), windowDay: vi.fn(), createKeyDate: vi.fn(),
}))
vi.mock("./api", async (orig) => ({ ...(await orig<object>()), patternAPI: { ...(await orig<{ patternAPI: object }>()).patternAPI, ...api } }))

import { TimelineWindowBar } from "./components/WindowPanel"

const day = {
  start: "2023-11-08T00:00:00-05:00", end: "2023-11-09T00:00:00-05:00", span: "day", zone: "America/New_York",
  zone_basis: "case_setting", zone_note: null, phones: [], phones_total: 0, date_only: "2023-11-08",
  money: [{ transaction_id: "t1", amount_minor: 39002, currency: "USD", counterparty: "Wren Pennywhistle", date_words: "Transaction date" }],
  money_total: 1,
}

function mount(selectedKey: string | null) {
  api.subjects.mockResolvedValue({ extractions: [{ last: "2024-05-01T10:00:00Z" }], total_extractions: 2 })
  api.keyDates.mockResolvedValue({ items: [] })
  api.windowDay.mockResolvedValue(day)
  api.window.mockResolvedValue({ ...day, span: "1h", date_only: null })
  const events = [
    { key: "pay-1", name: "Transfer To Wren Pennywhistle", type: "FinancialTransaction", at: null, date: "2023-11-08", payment: true },
    { key: "pay-2", name: "Transfer To Ellis Greywell", type: "FinancialTransaction", at: null, date: "2023-11-10", payment: true },
  ]
  render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <TimelineWindowBar caseId="case-1" events={events} selectedKey={selectedKey} />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe("the window around a payment", () => {
  it("opens the selected payment's whole day, says it has no time, and shows the Money lane", async () => {
    mount("pay-1")
    expect(await screen.findByText('The day of "Transfer To Wren Pennywhistle", 2023-11-08')).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "Open the window around this" }))
    expect(await screen.findByText("This payment has a date but no time. Showing the whole day.")).toBeTruthy()
    expect(await screen.findByRole("region", { name: "Lane: Money" })).toBeTruthy()
    expect(screen.getByText(/390\.02 USD · Wren Pennywhistle/)).toBeTruthy()
    expect(api.windowDay).toHaveBeenCalledWith("case-1", "2023-11-08", "case")
    expect(api.window).not.toHaveBeenCalled()
    // the whole day is fixed: no time-of-day spans to pick
    expect(screen.queryByRole("button", { name: "±6 h" })).toBeNull()
    expect(document.body.textContent).not.toMatch(/—/)
    // saving the moment keeps the day's start in the case zone (the server's midnight), never midnight UTC
    vi.spyOn(window, "prompt").mockReturnValue("Payment day")
    api.createKeyDate.mockResolvedValue({})
    fireEvent.click(screen.getByRole("button", { name: "Save this moment as a key date" }))
    await screen.findByText("Saved as a key date in Workspace.")
    expect(api.createKeyDate).toHaveBeenCalledWith("case-1", { kind: "date", label: "Payment day", instant: "2023-11-08T00:00:00-05:00", zone: "America/New_York" })
  })

  it("with no payment selected, keeps the timed anchor and never says the sentence", async () => {
    mount(null)
    fireEvent.click(await screen.findByRole("button", { name: "Open the window around this" }))
    expect(await screen.findByRole("region", { name: "Lane: Money" })).toBeTruthy()
    expect(api.window).toHaveBeenCalled()
    expect(screen.queryByText("This payment has a date but no time. Showing the whole day.")).toBeNull()
  })
})
