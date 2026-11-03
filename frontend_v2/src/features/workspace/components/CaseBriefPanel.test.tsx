import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { CaseBriefPanel, type CaseBrief } from "./CaseBriefPanel"

const mocks = vi.hoisted(() => ({ fetchAPI: vi.fn() }))
vi.mock("@/lib/api-client", () => ({ fetchAPI: mocks.fetchAPI }))

const clipped = <T,>(items: T[], not_shown = 0) => ({ count: items.length + not_shown, items, not_shown })

function brief(over: Partial<CaseBrief> = {}): CaseBrief {
  return {
    id: "b2", created_at: "2026-11-03T20:00:00Z", checked_at: "2026-11-03T21:00:00Z", trigger: "import",
    ledger_revision: "abcdef0123456789", out_of_date: false, out_of_date_sentence: null,
    changes: {
      first: false, something_changed: true,
      leads_closed: clipped([{ sentence: "Statements now cover 29 of the 29 missing days for Bank ending 0100 between 2024-01-31 and 2024-03-01." }]),
      leads_opened: clipped([], 0),
      open_leads: { missing_periods: 2, missing_days: 61, missing_accounts: 1, phone_leads: 0 },
      newly_testable: { spans: clipped([{ sentence: "Bank ending 0100 is now covered by statements from 2024-02-01 to 2024-02-29.", days: 29 }], 3), days: 29,
        phone_readings_decided: clipped([]), phone_readings_contradicted: 0 },
      totals: { before_revision: "11111111aaaa", after_revision: "22222222bbbb", available: true, reason: null,
        basis: "Verified totals count only payments from statements whose own arithmetic proves them.",
        verified_rows: 0, working_rows: 5, outside_verified_rows: 5,
        currencies: [{ population: "working", currency: "USD", changed: true, rows_change: 2,
          before: { rows: 3, credits_minor: "100000", debits_minor: "40000", net_minor: "60000" },
          after: { rows: 5, credits_minor: "150000", debits_minor: "40000", net_minor: "110000" } }], changed: 1 },
      judgement_calls: { open: 3, open_before: 2, added_open: 1, resolved: 0, added_by_rule: { "r.date": 1 } },
      conclusions_changed: clipped([{ kind: "hypothesis", id: "e1", title: "Rent", sentence: "Hypothesis “Rent” cites 1 ledger row that changed since the last brief.", rows: [{ id: "t1" }] }]),
      conclusions: { total: 1, hypotheses_open: 1, citing_rows: 1, rows_cited: 1 },
    },
    coverage: { statements_admitted: 4, accounts: 2, accounts_read: 2, ledger_rows_verified: 0, ledger_rows_working: 5, phones: 0,
      conclusions: 1, importing: 0, not_read: [], questions: ["verified and working totals per currency"] },
    cost: { seconds: 1.234, model_calls: 0 },
    ...over,
  }
}

const show = (canEdit = true) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <CaseBriefPanel caseId="case-1" canEdit={canEdit} />
    </QueryClientProvider>,
  )

describe("What changed brief", () => {
  it("shows closed leads, newly testable days with the count left out, totals before and after with revisions", async () => {
    mocks.fetchAPI.mockResolvedValue({ brief: brief(), requested_at: null })
    show()
    expect(await screen.findByText(/Statements now cover 29 of the 29 missing days/)).toBeInTheDocument()
    expect(screen.getByText("Current")).toBeInTheDocument()
    expect(screen.getByText("3 more items not shown here.")).toBeInTheDocument()
    expect(screen.getByText("1000.00 USD → 1500.00 USD")).toBeInTheDocument()
    expect(screen.getByText(/Ledger revision 11111111 → 22222222/)).toBeInTheDocument()
    expect(screen.getByText(/all 5 payments were accepted after review/)).toBeInTheDocument()
    expect(screen.getByText(/1 added and 0 confirmed or corrected/)).toBeInTheDocument()
    expect(screen.getByText(/Hypothesis “Rent” cites 1 ledger row/)).toBeInTheDocument()
    expect(screen.getByText(/no AI model was used/)).toBeInTheDocument()
    expect(mocks.fetchAPI).toHaveBeenCalledWith("/api/case-briefs/latest?case_id=case-1")
  })

  it("says a brief older than its newest evidence is out of date", async () => {
    mocks.fetchAPI.mockResolvedValue({ brief: brief({ out_of_date: true, out_of_date_sentence: "Out of date: evidence changed at 2026-11-03T22:00:00Z, after this brief was made." }), requested_at: null })
    show()
    expect(await screen.findByText("Out of date")).toBeInTheDocument()
    expect(screen.getByText(/evidence changed at 2026-11-03T22:00:00Z/)).toBeInTheDocument()
  })

  it("asks for a new brief with Check now, and only when the user can edit", async () => {
    mocks.fetchAPI.mockReset()
    mocks.fetchAPI.mockImplementation((url: string) => Promise.resolve(url.endsWith("/run") ? { requested: true } : { brief: null, requested_at: null }))
    show()
    expect(await screen.findByText(/No brief yet/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /Check now/ }))
    await vi.waitFor(() => expect(mocks.fetchAPI).toHaveBeenCalledWith("/api/case-briefs/run", { method: "POST", body: { case_id: "case-1" } }))
  })

  it("has no Check now button for a viewer", async () => {
    mocks.fetchAPI.mockResolvedValue({ brief: brief(), requested_at: null })
    show(false)
    await screen.findByText("Current")
    expect(screen.queryByRole("button", { name: /Check now/ })).not.toBeInTheDocument()
  })
})
