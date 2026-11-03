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

  it("shows the day's bank notification on the phone, never as a device event, and never calls its hour No data", async () => {
    const ev = (id: number, at: string, record_type: string, field: string, family: string) => ({
      ref_kind: "activity_event", id, at, end: null, field, meaning: "event_instant", class: "passive", strength: "none",
      actor: "owner", flags: [], source_app: null, extraction_id: "p1", phone: "Phone 1", record_uid: `r${id}`, record_type, family })
    const hours = Array.from({ length: 24 }, (_, h) => ({ hour_utc: `2023-11-08T${String(h).padStart(2, "0")}:00:00Z`, state: "no_data",
      has_records: h === 1 || h === 10, words: h === 1 || h === 10 ? "No continuous recording; records this hour" : "No data" }))
    const phone = {
      extraction_id: "p1", label: "Phone 1", availability: [{ extraction_id: "p1", phone: "Phone 1", hours }],
      lanes: { interaction: [], device_state: [], communications: [], places: [], others: [], money: [], passive: [
        ev(1, "2023-11-08T01:21:19Z", "Cookie", "CreationTime", "web"),
        ev(2, "2023-11-08T10:00:00Z", "Notification", "TimeStamp", "notifications"),
        ev(3, "2023-11-08T10:05:00Z", "WirelessNetwork", "TimeStamp", "wifi"),
        ev(4, "2023-11-08T10:06:00Z", "InstantMessage", "TimeStamp", "messages")] },
      totals: { interaction: 0, device_state: 0, communications: 0, places: 0, others: 0, money: 0, passive: 4 },
      lane_words: {}, truncated: false, passive_as_hourly_counts: false, passive_hours: null, limit_words: null,
    }
    mount("pay-1")
    api.windowDay.mockResolvedValue({ ...day, start: "2023-11-08T00:00:00Z", end: "2023-11-09T00:00:00Z", zone: "UTC", phones: [phone], phones_total: 1 })
    fireEvent.click(await screen.findByRole("button", { name: "Open the window around this" }))
    const recorded = await screen.findByRole("region", { name: "Lane: Phone 1: recorded without use" })
    expect(recorded.textContent).toMatch(/2 items/)
    expect(recorded.querySelector('[title*="Notification · TimeStamp"]')).toBeTruthy()
    expect(screen.getByText("1 device event or sensor reading and 1 time of a message or call already shown hidden.")).toBeTruthy()
    const lane = screen.getByRole("region", { name: "Lane: Phone 1" })
    expect(lane.textContent).toMatch(/No continuous recording; records this hour/)
    expect(lane.textContent).toMatch(/No data/)
  })
})
