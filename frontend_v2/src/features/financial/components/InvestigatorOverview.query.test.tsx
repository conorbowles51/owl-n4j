import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, expect, it, vi } from "vitest"
import { InvestigatorOverview } from "./InvestigatorOverview"

const row = (key: string, direction: "credit" | "debit", amount: string, category: string, currency = "MXN") => ({
  key,
  case_id: "case",
  account_id: "acct",
  account_label: "BBVA 0118",
  direction,
  amount_minor: amount,
  currency,
  category,
  ordering_date: "2025-03-04",
  ordering_date_context: "transaction",
})
const rows = [
  row("a", "credit", "500000", "Transfers"),
  row("b", "debit", "120000", "Uncategorized"),
  row("c", "debit", "1000", "Bank fees", "USD"),
]
// The server's figures over these rows (GET /ledger-overview): MXN in 5,000.00 / out 1,200.00 (2 payments), USD out 10.00.
const totals = {
  case_id: "case",
  complete: true,
  categories: [],
  payments: 3,
  accounts: 1,
  unknown_dates: 0,
  uncategorised: 1,
  first_day: "2025-03-04",
  last_day: "2025-03-04",
  currencies: [
    { currency: "USD", payments: 1, credit: "0", debit: "1000" },
    { currency: "MXN", payments: 2, credit: "500000", debit: "120000" },
  ],
}
// The server's lower panels over the same rows (GET /ledger-overview-panels), already in the page's order.
const panels = {
  case_id: "case",
  complete: true,
  categories: [],
  totals: {
    payments: 3,
    inventory: { accounts: [{ id: "acct", label: "BBVA 0118", currencies: ["MXN", "USD"] }], banks: [], currencies: ["MXN", "USD"],
      first: "2025-03-04", last: "2025-03-04", undated: 0, unknown_banks: 1, unidentified_counterparties: 3 },
    groups: [{ group: "MXN:bank", credit: "500000", debit: "120000", count: 2, accounts: 1 },
      { group: "USD:bank", credit: "0", debit: "1000", count: 1, accounts: 1 }],
    unreadable: 0,
  },
  connections: { payments: 3, groups: [] },
  comparisons: { pairs: 1, keys: ["a", "b"] },
}
// "stale": a background refetch failed while the query still holds its last answer (isError with data).
type Status = "ready" | "pending" | "error" | "stale"
const state = vi.hoisted(() => ({
  panels: "ready" as Status,
  totals: "ready" as Status,
  register: "ready" as Status,
  findings: "ready" as Status,
  calls: "ready" as Status,
  openCalls: 7,
  uncategorised: 1,
  registerDone: false,
  loadedEveryPayment: false,
}))
// The Overview no longer reads every payment: reading them is recorded so a test fails if it comes back.
vi.mock("../hooks/use-investigator-payments", () => ({
  useInvestigatorPayments: () => {
    state.loadedEveryPayment = true
    return { rows, complete: true, query: { isPending: false, isError: false, refetch: vi.fn() } }
  },
}))
vi.mock("../hooks/use-ledger-overview", () => ({
  useLedgerOverview: () => ({
    data: (state.totals === "ready" || state.totals === "stale") ? { ...totals, uncategorised: state.uncategorised } : undefined,
    isPending: state.totals === "pending",
    isError: state.totals === "error" || state.totals === "stale",
    isSuccess: state.totals === "ready",
    refetch: vi.fn(),
  }),
  usePanelFigureKeys: () => vi.fn(),
  useLedgerOverviewPanels: () => ({
    data: (state.panels === "ready" || state.panels === "stale") ? panels : undefined,
    isPending: state.panels === "pending",
    isError: state.panels === "error" || state.panels === "stale",
    error: state.panels !== "ready" && state.panels !== "pending" ? Error("The payments could not be loaded.") : null,
    refetch: vi.fn(),
  }),
}))
vi.mock("../hooks/use-statement-register", () => ({
  useStatementRegister: () => ({
    files: {
      data: (state.register === "ready" || state.register === "stale") ? [{ id: "f1" }, { id: "f2" }] : undefined,
      isPending: state.register === "pending",
      isError: state.register === "error" || state.register === "stale",
      refetch: vi.fn(),
    },
    imports: {
      data:
        state.register === "ready" || state.register === "stale"
          ? state.registerDone
            ? { truncated: false, files: ["f1", "f2"].map((id) => ({ evidence_file_id: id, current_transactions: 3, periods: [{}], available_periods: 0, periods_with_checks: 0 })) }
            : { truncated: false, files: [{ evidence_file_id: "f1", current_transactions: 3, periods: [{}], available_periods: 0, periods_with_checks: 2 }] }
          : undefined,
      isPending: state.register === "pending",
      isError: state.register === "error" || state.register === "stale",
      refetch: vi.fn(),
    },
  }),
}))
vi.mock("@/features/workspace/hooks/use-casework", () => ({
  useCaseworkEntries: () => ({
    isPending: state.findings === "pending",
    isError: state.findings === "error" || state.findings === "stale",
    isSuccess: state.findings === "ready",
    refetch: vi.fn(),
    data: (state.findings === "ready" || state.findings === "stale") ? { entries: [], total: 0 } : undefined,
  }),
}))
// Loupe's calls come through the real hook and a real QueryClient; only the request is replaced.
const counts = vi.hoisted(() => ({ fail: false, resolveNext: null as null | (() => void), calls: 0 }))
vi.mock("../lib/judgements", async (original) => ({
  ...(await original<typeof import("../lib/judgements")>()),
  judgementCounts: () => {
    counts.calls += 1
    if (counts.fail) return Promise.reject(Error("The calls could not be counted."))
    if (counts.resolveNext) {
      return new Promise((resolve) => {
        counts.resolveNext = () => resolve({ case: { total: 9, open: 7, inferred: 4 } })
      })
    }
    return Promise.resolve({ case: { total: 9, open: 7, inferred: 4 } })
  },
}))
vi.mock("../hooks/use-financial-access", () => ({ useFinancialAccess: () => ({ canEdit: true }) }))
vi.mock("./InvestigatorFollowMoney", () => ({
  MoneyConnectionsView: ({ payments }: { payments: number }) => <p>Connections over {payments} payments</p>,
}))
vi.mock("./OverviewStatementCoverage", () => ({ OverviewStatementCoverage: () => <p>Coverage grid</p> }))
vi.mock("./InvestigationWorkspaceParts", async (original) => ({
  ...(await original<typeof import("./InvestigationWorkspaceParts")>()),
  WorkspaceScope: () => <p>Scope</p>,
}))
vi.mock("./InvestigationTransactionTable", () => ({
  PaymentTotalsView: ({ label, payments, totals }: { label: string; payments: number; totals: Map<string, { credit: bigint }> }) => (
    <p>{label}<span>{`${payments} totalled · MXN in ${totals.get("MXN:bank")?.credit}`}</span></p>
  ),
}))
vi.mock("./PaymentComparison", () => ({
  PaymentComparison: ({ ids, title }: { ids: string[]; title: string }) => <p>{`${title}: ${ids.join(",")}`}</p>,
}))
afterEach(() => {
  cleanup()
  counts.fail = false
  counts.resolveNext = null
  counts.calls = 0
})

// The Overview's note depends on how React Query reports a failed background refresh: isError true with the last
// answer still held, and isFetching while it is fetched again. The other tests stand those flags in by hand.
it("with a real query: a failed refresh keeps the count, names it, and says so while it loads again", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <InvestigatorOverview caseId="case" />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  const progress = () => screen.getByRole("list", { name: "Your progress on this case" }).textContent
  await waitFor(() => expect(progress()).toContain("7 of Loupe's calls open"))
  expect(screen.queryByText(/could not be updated/)).toBeNull()

  counts.fail = true
  await act(() => client.refetchQueries({ queryKey: ["financial-judgements"] }).catch(() => undefined))
  await waitFor(() => expect(screen.getByText(/could not be updated/).textContent).toContain("Loupe's calls"))
  expect(progress()).toContain("7 of Loupe's calls open")

  counts.fail = false
  counts.resolveNext = () => undefined
  fireEvent.click(screen.getByRole("button", { name: "Load them again" }))
  const busy = await screen.findByRole("button", { name: "Loading them again…" })
  expect((busy as HTMLButtonElement).disabled).toBe(true)
  await act(async () => counts.resolveNext?.())
  await waitFor(() => expect(screen.queryByText(/could not be updated/)).toBeNull())
  expect(progress()).toContain("7 of Loupe's calls open")
})
