import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 05 section 3.9 (AP-1) for approach 1, and the ledger side of 4.4. Invented data only. */
const api = vi.hoisted(() => ({
  moneyAPI: {
    runs: vi.fn(), request: vi.fn(), run: vi.fn(), cancel: vi.fn(), coverage: vi.fn(), results: vi.fn(), detail: vi.fn(),
    decide: vi.fn(), ledgerLinks: vi.fn(), decidePair: vi.fn(), orphaned: vi.fn(),
  },
}))
vi.mock("./money-api", () => api)
const perms = vi.hoisted(() => ({ canEdit: true }))
vi.mock("@/hooks/use-permissions", () => ({ usePermissions: () => ({ canEdit: perms.canEdit }) }))
vi.mock("@/features/pattern/components/CollectBar", () => ({ CollectBar: () => <div>Add to…</div> }))

import MoneySignalsPage, { WHAT_IT_DOES } from "./MoneySignalsPage"
import { amountWords } from "./money-words"
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

const SEARCH = "Every payment within 31 days and within half of the amount (at least 5.00) is listed, strongest first; payments outside that are counted, not hidden."
const PAIR = (over: Record<string, unknown>) => ({
  transaction_id: "tx-1", ref_id: "T-1", amount_minor: 1250, currency: "USD", date: "2024-03-02", lag_days: 0, level: "strong",
  reasons: { match: ["same amount to the cent", "same day", "account fits by bank and ending"],
    substantiation: ["the notification on the phone", "the bank's usual alert wording"] },
  found_by_rule: true, rule_words: "found by the rule, strength strong", decision: null, decision_words: null, ...over })
const PAIRED = { ...READING, measures: { ...READING.measures, record_uid: "rec-1", field_path: "Body", best_level: "strong",
  pairings: [PAIR({}),
    PAIR({ transaction_id: "tx-2", ref_id: "T-2", date: "2024-03-10", lag_days: 8, level: "weak", rule_words: "found by the rule, strength weak",
      reasons: { match: ["same amount to the cent", "payment 8 days after the phone record", "account fits by bank and ending"], substantiation: ["the notification on the phone"] } }),
    PAIR({ transaction_id: "tx-3", ref_id: "T-3", level: "faint", decision: "rejected", decision_words: "rejected by Synthetic Reviewer: Refund", rule_words: "found by the rule, strength faint" })],
  pair_counts: { by_level: { strong: 1, moderate: 0, weak: 1, faint: 0 }, confirmed: 0, rejected: 1 },
  pairings_left_out_words: "Not listed: payments on these accounts 1 more than 31 days away." } }

function page() {
  api.moneyAPI.runs.mockResolvedValue({ items: [RUN] })
  api.moneyAPI.coverage.mockResolvedValue({ sentence: RUN.coverage.sentence })
  api.moneyAPI.orphaned.mockResolvedValue({ items: [], search: SEARCH })
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

  it("records a lead as not pursued with a reason and shows it in the result's decision history (07 section 14)", async () => {
    page()
    api.moneyAPI.decide.mockClear()
    fireEvent.click(await screen.findByRole("button", { name: /USD 12.50 out/ }))
    fireEvent.click(screen.getByRole("button", { name: "Not pursued" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Say why, in your own words.")
    expect(api.moneyAPI.decide).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "Family transfer, outside this enquiry" } })
    const decided = { ...READING, decision: "not_pursued", decisions: [
      { decision: "not_pursued", reason: "Family transfer, outside this enquiry", by: "Synthetic Reviewer", at: "2026-11-03T22:00:00Z" }] }
    api.moneyAPI.decide.mockResolvedValue(decided)
    api.moneyAPI.results.mockResolvedValue({ total: 1, offset: 0, limit: 100, items: [decided] })
    fireEvent.click(screen.getByRole("button", { name: "Not pursued" }))
    await waitFor(() => expect(api.moneyAPI.decide).toHaveBeenCalledWith("c1", "res-1", "not_pursued", "Family transfer, outside this enquiry"))
    expect(await screen.findByText("Not pursued by Synthetic Reviewer: Family transfer, outside this enquiry")).toBeInTheDocument()
  })

  it("lists several possible payments without linking any of them", async () => {
    page()
    const several = { ...READING, measures: { ...READING.measures, outcome: "several_candidates", reason: "several_payments_match" } }
    api.moneyAPI.results.mockResolvedValue({ total: 1, offset: 0, limit: 100, items: [several] })
    api.moneyAPI.detail.mockResolvedValue({ ...several, records: [
      { record_uid: "rec-1", extraction_id: "e1", field_path: "Body", ledger_transaction_id: null, ledger_ref_id: null, role: "evidence" },
      { record_uid: null, extraction_id: null, field_path: null, ledger_transaction_id: "tx-1", ledger_ref_id: "T-1", role: "ledger_candidate" },
      { record_uid: null, extraction_id: null, field_path: null, ledger_transaction_id: "tx-2", ledger_ref_id: "T-2", role: "ledger_candidate" }] })
    expect(await screen.findByText(/Several payments could be this one/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /USD 12.50 out/ }))
    expect(await screen.findByText("Payments that could be this one. None is linked to it.")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Open possible payment T-2" })).toHaveAttribute("href", "/cases/c1/financial?payment=tx-2")
    expect(screen.queryByRole("link", { name: /^Open payment/ })).toBeNull()
  })

  it("lists every payment that could match, strongest first, with strength, reasons and what was left out (05 4.3.8)", async () => {
    page()
    api.moneyAPI.results.mockResolvedValue({ total: 1, offset: 0, limit: 100, items: [PAIRED] })
    const pairs = await screen.findAllByTestId("money-pair")
    expect(pairs.map((p) => within(p).getByTestId("pair-level").textContent)).toEqual(["Strong", "Weak", "Faint"])
    expect(within(pairs[1]).getByTestId("pair-status").textContent).toBe("found by the rule, strength weak")
    expect(within(pairs[1]).getByTestId("pair-matched").textContent).toContain("payment 8 days after the phone record")
    expect(within(pairs[0]).getByTestId("pair-substantiated").textContent).toMatch(/^Substantiated by 2 sources/)
    expect(screen.getByTestId("pair-left-out").textContent).toContain("1 more than 31 days away")
    expect(screen.getByTestId("search-bound").textContent).toBe(SEARCH)
    // rejected stays visible, collapsed, and is left out of the counts
    expect(pairs[2].getAttribute("data-decision")).toBe("rejected")
    expect(within(pairs[2]).getByText("rejected by Synthetic Reviewer: Refund. Not counted.")).toBeInTheDocument()
    expect(screen.getByTestId("pair-summary").textContent).toContain("strong 1, moderate 0, weak 1, faint 0")
    expect(screen.getByTestId("pair-summary").textContent).toContain("1 rejected by a person and not counted")
    expect(screen.getByText(/2 payments in the financial records could be this one/)).toBeInTheDocument()
  })

  it("confirms, rejects with an optional note and undoes a match; a viewer gets no buttons", async () => {
    page()
    api.moneyAPI.results.mockResolvedValue({ total: 1, offset: 0, limit: 100, items: [PAIRED] })
    api.moneyAPI.decidePair.mockResolvedValue({ decision: "confirmed", decision_words: "confirmed by Synthetic Reviewer 2026-11-04" })
    fireEvent.click(await screen.findByRole("button", { name: "Confirm the match with payment T-1" }))
    await waitFor(() => expect(api.moneyAPI.decidePair).toHaveBeenCalledWith("c1", "rec-1", "Body", "tx-1", "confirmed", ""))
    const weak = screen.getAllByTestId("money-pair")[1]
    fireEvent.click(within(weak).getByText("Add a note"))
    fireEvent.change(within(weak).getByLabelText("Note"), { target: { value: "Different merchant" } })
    fireEvent.click(within(weak).getByRole("button", { name: "Reject the match with payment T-2" }))
    await waitFor(() => expect(api.moneyAPI.decidePair).toHaveBeenCalledWith("c1", "rec-1", "Body", "tx-2", "rejected", "Different merchant"))
    fireEvent.click(screen.getByRole("button", { name: "Undo the decision on payment T-3" }))
    await waitFor(() => expect(api.moneyAPI.decidePair).toHaveBeenCalledWith("c1", "rec-1", "Body", "tx-3", "undo", ""))
  })

  it("shows a confirmed match as confirmed by its person, and a viewer sees no decision buttons", async () => {
    perms.canEdit = false
    page()
    const confirmed = { ...PAIRED, measures: { ...PAIRED.measures, pairings: [PAIR({ decision: "confirmed", decision_words: "confirmed by Synthetic Reviewer 2026-11-04" })] } }
    api.moneyAPI.results.mockResolvedValue({ total: 1, offset: 0, limit: 100, items: [confirmed] })
    const pair = await screen.findByTestId("money-pair")
    expect(within(pair).getByTestId("pair-status").textContent).toBe("confirmed by Synthetic Reviewer 2026-11-04")
    expect(within(pair).queryByRole("button")).toBeNull()
    perms.canEdit = true
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
