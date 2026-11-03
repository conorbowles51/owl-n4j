import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 05 section 3.9 (AP-1) for approach 1, and the ledger side of 4.4. Invented data only. */
const api = vi.hoisted(() => ({
  moneyAPI: {
    runs: vi.fn(), request: vi.fn(), run: vi.fn(), cancel: vi.fn(), coverage: vi.fn(), results: vi.fn(), detail: vi.fn(),
    decide: vi.fn(), ledgerLinks: vi.fn(),
  },
}))
vi.mock("./money-api", () => api)
vi.mock("@/features/pattern/components/CollectBar", () => ({ CollectBar: () => <div>Add to…</div> }))

import MoneySignalsPage, { WHAT_IT_DOES, amountWords } from "./MoneySignalsPage"
import { PhoneMentions } from "@/features/financial/components/PhoneMentions"

const RUN = { id: "run-1", approach: "money_signals", status: "completed", progress: {}, counts: {}, error: null,
  coverage: { sentence: "Notifications exist on 1 of 2 phones (C1). Results below cover those phones only." },
  created_at: "2026-11-03T08:00:00Z", finished_at: "2026-11-03T08:01:00Z" }
const READING = {
  id: "res-1", kind: "money_reading", strength: "institution_template", label: "Lead for enquiry", decision: null, decisions: [],
  period_start: "2024-03-02T15:00:00Z",
  measures: { amount_minor: 1250, currency: "USD", amount_text: "$12.50", direction: "debit", source: "notification",
    phone_label: "C1", event_instant: "2024-03-02T15:00:00Z", device_zone: "UTC", outcome: "corroborated", reason: null,
    institution: { id: "inst:synthbank", name: "Synthetic Bank" }, account_ref: "ending 1234" },
  directions: { supports: [], undercuts: [] },
}

function page() {
  api.moneyAPI.runs.mockResolvedValue({ items: [RUN] })
  api.moneyAPI.coverage.mockResolvedValue({ sentence: RUN.coverage.sentence })
  api.moneyAPI.results.mockResolvedValue({ total: 1, offset: 0, limit: 100, items: [READING] })
  api.moneyAPI.detail.mockResolvedValue({ ...READING, records: [
    { record_uid: "rec-1", extraction_id: "e1", field_path: "Body", ledger_transaction_id: null, ledger_ref_id: null, role: "evidence" },
    { record_uid: null, extraction_id: null, field_path: null, ledger_transaction_id: "tx-1", ledger_ref_id: "T-1", role: "ledger_match" }] })
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/cases/c1/phone-money"]}>
        <Routes><Route path="/cases/:id/phone-money" element={<MoneySignalsPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>)
}

describe("Money on the phones (AP-1)", () => {
  it("shows the parts in order, the run's coverage, the total and the label on every result", async () => {
    page()
    await screen.findByTestId("money-result")
    const parts = Array.from(document.querySelectorAll("[data-part]")).map((e) => e.getAttribute("data-part"))
    expect(parts).toEqual(["what", "run", "coverage", "results"])
    expect(screen.getByText(WHAT_IT_DOES)).toBeInTheDocument()
    expect(screen.getByText(RUN.coverage.sentence)).toBeInTheDocument()
    expect(screen.getByTestId("money-total").textContent).toBe("1 result.")
    for (const r of screen.getAllByTestId("money-result")) expect(within(r).getByText("Lead for enquiry")).toBeInTheDocument()
    expect(screen.getByText(/From the phone, not a statement/)).toBeInTheDocument()
  })

  it("lead copy on screen has no em dash and never says what to ask for or from whom (05 4.9 test 12)", async () => {
    page()
    api.moneyAPI.results.mockResolvedValue({ total: 1, offset: 0, limit: 100, items: [{ ...READING, id: "lead-1",
      kind: "account_lead", strength: "presence", measures: { institution: { name: "Synthetic Bank" }, status: "no_statement_found",
        sentence: "This phone had signs of Synthetic Bank on it. No account at Synthetic Bank is among the financial records in this case." } }] })
    fireEvent.click(await screen.findByRole("tab", { name: "Accounts the financial records do not include" }))
    await screen.findByText(/This phone had signs of Synthetic Bank/)
    expect(document.body.textContent).not.toMatch(/—|subpoena|request|obtain/i)
  })

  it("opens the phone record and the matched payment, offers Add to…, and refuses a reject without a reason", async () => {
    page()
    fireEvent.click(await screen.findByRole("button", { name: /USD 12.50 out/ }))
    expect(await screen.findByRole("link", { name: "Open the phone record" })).toHaveAttribute("href", "/cases/c1/records/rec-1")
    expect(screen.getByRole("link", { name: "Open payment T-1" })).toHaveAttribute("href", "/cases/c1/financial?payment=tx-1")
    expect(screen.getByText("Add to…")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Reject" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Say why, in your own words.")
    expect(api.moneyAPI.decide).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "Not this card" } })
    api.moneyAPI.decide.mockResolvedValue(READING)
    fireEvent.click(screen.getByRole("button", { name: "Reject" }))
    await waitFor(() => expect(api.moneyAPI.decide).toHaveBeenCalledWith("c1", "res-1", "rejected", "Not this card"))
  })

  it("writes amounts from integer minor units by the currency's exponent, and the text as written when unknown", () => {
    expect(amountWords({ amount_minor: 123456, currency: "USD" })).toBe("USD 1,234.56")
    expect(amountWords({ amount_minor: 1500, currency: "JPY" })).toBe("JPY 1,500")
    expect(amountWords({ amount_minor: 5, currency: "USD" })).toBe("USD 0.05")
    expect(amountWords({ amount_minor: null, currency: null, amount_text: "$1,234" })).toBe("$1,234 (as written)")
  })
})

describe("Also recorded on phone (05 4.4)", () => {
  it("links a payment to the phone record that corroborates it, and says it is a reading from the phone", async () => {
    const id = "11111111-2222-4333-8444-555555555555"
    api.moneyAPI.ledgerLinks.mockResolvedValue({ links: { [id]: [{ phone_label: "C1", source: "notification",
      instant: "2024-03-02T15:00:00Z", record_uid: "rec-1", url: "/cases/c1/records/rec-1", result_id: "res-1",
      outcome: "corroborated" }] } })
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter><PhoneMentions caseId="c1" transactionId={id} /></MemoryRouter>
      </QueryClientProvider>)
    const box = await screen.findByTestId("phone-mentions")
    expect(box.textContent).toMatch(/^Also recorded on phone C1: notification at .+2024/)
    expect(within(box).getByRole("link", { name: "Open the phone record" })).toHaveAttribute("href", "/cases/c1/records/rec-1")
    expect(box.textContent).not.toMatch(/—|subpoena|request|obtain/i)
  })

  it("asks nothing for a row whose key is not a payment id", () => {
    api.moneyAPI.ledgerLinks.mockClear()
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter><PhoneMentions caseId="c1" transactionId="candidate:7" /></MemoryRouter>
      </QueryClientProvider>)
    expect(api.moneyAPI.ledgerLinks).not.toHaveBeenCalled()
  })
})
