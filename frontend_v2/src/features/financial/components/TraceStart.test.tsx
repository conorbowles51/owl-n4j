import { useFinancialDraftStore } from "../stores/financial-drafts"
import { cleanup, fireEvent, render as renderUI, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { LedgerTransaction } from "../api"
import { LedgerTracingWorkbench } from "./LedgerTracingWorkbench"
import { fetchAPI } from "@/lib/api-client"
import { traceStartFrom, writeTraceStart } from "../lib/trace-start"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("./RequestedCoveragePanel", () => ({ RequestedCoveragePanel: () => null }))
const payments = vi.hoisted(() => ({
  value: { complete: true, rows: [] as unknown[], query: { isError: false, isPending: false, isFetching: false, data: { transactions: [] as unknown[] }, refetch: () => {} } },
}))
vi.mock("../hooks/use-investigator-payments", () => ({ useInvestigatorPayments: () => payments.value }))

function render(ui: ReactNode) {
  return renderUI(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>)
}
const row = (key: string, direction: string, amount: string, day: string, extra: Partial<LedgerTransaction> = {}) =>
  ({ key, case_id: "case", direction, amount_minor: amount, currency: "MXN", account_id: "a1", account_label: "BBVA 0118", ordering_date: day, ordering_date_context: "transaction", ...extra }) as unknown as LedgerTransaction
function holds(rows: LedgerTransaction[]) {
  payments.value = { complete: true, rows, query: { isError: false, isPending: false, isFetching: false, data: { transactions: rows }, refetch: () => {} } }
}
const big = row("big", "credit", "1000000", "2025-04-28", { from_name: "ECOTERRA" })

beforeEach(() => {
  useFinancialDraftStore.setState({ drafts: {} })
  vi.mocked(fetchAPI).mockReset()
})
afterEach(cleanup)

describe("Trace where it went, from Follow money", () => {
  it("opens on the clicked payment: account and dates filled, first step shown and the trace request sent with no click", async () => {
    const rows = [
      big,
      row("before", "debit", "5", "2025-04-01"),
      row("o1", "debit", "600000", "2025-04-29", { to_name: "INDHECA" }),
      row("other-account", "debit", "9", "2025-05-01", { account_id: "a2" }),
      row("o2", "debit", "500000", "2025-05-03", { to_name: "Payroll" }),
      row("last", "credit", "1", "2026-08-31"),
    ]
    holds(rows)
    vi.mocked(fetchAPI).mockReturnValue(new Promise(() => {}))
    writeTraceStart("case", traceStartFrom(big, rows, {}))
    render(<LedgerTracingWorkbench caseId="case" />)
    const step = screen.getByRole("region", { name: "Where it went next" })
    expect(step.textContent).toContain("into BBVA 0118")
    expect(step.textContent).toContain("2 payments out of BBVA 0118 from 2025-04-28 to 2026-08-31")
    expect(step.textContent).toContain("The first 2 of them, in date order, add up to")
    expect(screen.getByText("INDHECA")).toBeTruthy()
    expect(screen.queryByText("other-account")).toBeNull()
    await waitFor(() => expect(fetchAPI).toHaveBeenCalled())
    const url = String(vi.mocked(fetchAPI).mock.calls[0][0])
    expect(url).toContain("/api/financial/ledger-trace-inputs?case_id=case")
    expect(url).toContain("population=working&account_id=a1&start_date=2025-04-28&end_date=2026-08-31")
    expect(screen.getByText(/Loading the payments of this account from 2025-04-28 to 2026-08-31 for the tracing rules… \d+ s/)).toBeTruthy()
  })

  it("says plainly when nothing left the account, and what to do", () => {
    const rows = [big, row("earlier", "debit", "5", "2025-04-01")]
    holds(rows)
    vi.mocked(fetchAPI).mockReturnValue(new Promise(() => {}))
    writeTraceStart("case", traceStartFrom(big, rows, { endDate: "2025-12-31" }))
    render(<LedgerTracingWorkbench caseId="case" />)
    expect(
      screen.getByText(/No payments out of BBVA 0118 from 2025-04-28 to 2025-12-31 in the statements loaded\. If money left later/)
    ).toBeTruthy()
  })

  it("shows a refusal of nothing to trace as the reason with Retry, not as a whole-case run", async () => {
    holds([big])
    vi.mocked(fetchAPI).mockRejectedValue(new Error("No verified payments to trace in this account from 2025-04-28 to 2025-04-28: 3 imported payments are not verified yet."))
    writeTraceStart("case", traceStartFrom(big, [big], {}))
    render(<LedgerTracingWorkbench caseId="case" />)
    expect((await screen.findByRole("alert")).textContent).toContain("No verified payments to trace")
    vi.mocked(fetchAPI).mockReturnValue(new Promise(() => {}))
    fireEvent.click(screen.getByRole("button", { name: "Retry" }))
    expect(fetchAPI).toHaveBeenCalledTimes(2)
  })

  it("shows the first step of a 30,000-payment case within 2 s", () => {
    const rows = [big]
    for (let i = 0; i < 30000; i++)
      rows.push(row(`r${i}`, i % 2 ? "debit" : "credit", String(1000 + i), `2025-${String(1 + (i % 12)).padStart(2, "0")}-${String(1 + (i % 28)).padStart(2, "0")}`, { account_id: i % 3 ? "a1" : "a2" }))
    holds(rows)
    vi.mocked(fetchAPI).mockReturnValue(new Promise(() => {}))
    const t0 = performance.now()
    writeTraceStart("case", traceStartFrom(big, rows, {}))
    render(<LedgerTracingWorkbench caseId="case" />)
    const step = screen.getByRole("region", { name: "Where it went next" })
    expect(step.textContent).toMatch(/[\d,]+ payments out of BBVA 0118/)
    expect(step.textContent).toContain("Showing 25 of")
    expect(performance.now() - t0).toBeLessThan(2000)
  })
})
