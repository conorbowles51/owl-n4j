import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, expect, it, vi } from "vitest"
import { InvestigatorOverview } from "./InvestigatorOverview"
import { useFinancialStore } from "../stores/financial.store"

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
const state = vi.hoisted(() => ({
  panels: "ready" as "ready" | "pending" | "error",
  totals: "ready" as "ready" | "pending" | "error",
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
    data: state.totals === "ready" ? totals : undefined,
    isPending: state.totals === "pending",
    isError: state.totals === "error",
    isSuccess: state.totals === "ready",
  }),
  useLedgerOverviewPanels: () => ({
    data: state.panels === "ready" ? panels : undefined,
    isPending: state.panels === "pending",
    isError: state.panels === "error",
    error: state.panels === "error" ? Error("The payments could not be loaded.") : null,
    refetch: vi.fn(),
  }),
}))
vi.mock("../hooks/use-statement-register", () => ({
  useStatementRegister: () => ({
    files: { data: [{ id: "f1" }, { id: "f2" }], isPending: false, isError: false },
    imports: {
      data: { truncated: false, files: [{ evidence_file_id: "f1", current_transactions: 3, periods: [{}], available_periods: 0, periods_with_checks: 2 }] },
      isPending: false,
      isError: false,
    },
  }),
}))
vi.mock("@/features/workspace/hooks/use-casework", () => ({
  useCaseworkEntries: () => ({ isPending: false, isError: false, isSuccess: true, data: { entries: [], total: 0 } }),
}))
vi.mock("../hooks/use-judgements", () => ({
  useJudgementCounts: () => ({ isSuccess: true, isError: false, data: { case: { total: 9, open: 7, inferred: 4 } } }),
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
  state.panels = "ready"
  state.totals = "ready"
  state.loadedEveryPayment = false
})

it("leads with the next step, the journey, money by currency and every old panel", () => {
  render(
    <MemoryRouter>
      <InvestigatorOverview caseId="case" />
    </MemoryRouter>
  )
  expect(screen.getByRole("heading", { name: /2 statements need a check/ })).toBeTruthy()
  const progress = screen.getByRole("list", { name: "Your progress on this case" })
  expect(progress.textContent).toContain("Load(done)")
  expect(progress.textContent).toContain("Read(now)")
  expect(progress.textContent).toContain("7 of Loupe's calls open")
  expect(screen.getByText("1 payment has no category yet")).toBeTruthy()
  // currency switch: MXN first (2 payments), USD selectable
  expect(screen.getByRole("button", { name: "MXN · 2" }).getAttribute("aria-pressed")).toBe("true")
  expect(screen.getByText("+5.00 k")).toBeTruthy()
  fireEvent.click(screen.getByRole("button", { name: "USD · 1" }))
  expect(screen.getByText("−10")).toBeTruthy()
  // kept panels
  for (const text of ["Scope", "Connections over 3 payments", "Coverage grid", "Imported payments in the selected accounts and dates", "Saved investigation work", "Your statements", "Explore activity over time"])
    expect(screen.getByText(text)).toBeTruthy()
  expect(screen.getByRole("button", { name: "Add or review statements" })).toBeTruthy()
  fireEvent.click(screen.getByRole("button", { name: "Check the 2 statements →" }))
  expect(useFinancialStore.getState().mainView).toBe("statements")
})

it("shows the top figures from the server's totals while the panels are still loading", () => {
  state.panels = "pending"
  render(
    <MemoryRouter>
      <InvestigatorOverview caseId="case" />
    </MemoryRouter>
  )
  const progress = screen.getByRole("list", { name: "Your progress on this case" })
  expect(progress.textContent).toContain("3 payments · 1 uncategorised")
  expect(screen.getByText("1 payment has no category yet")).toBeTruthy()
  expect(screen.getByRole("button", { name: "MXN · 2" }).getAttribute("aria-pressed")).toBe("true")
  expect(screen.getByText("+5.00 k")).toBeTruthy()
  expect(screen.getByRole("status").textContent).toBe("Loading this case’s payments (3 payments)…")
})

it("draws the lower panels from the server's figures without reading every payment", () => {
  render(
    <MemoryRouter>
      <InvestigatorOverview caseId="case" />
    </MemoryRouter>
  )
  expect(state.loadedEveryPayment).toBe(false)
  expect(screen.getByText("3 totalled · MXN in 500000")).toBeTruthy()
  expect(screen.getByRole("heading", { name: /1 times money arrived/ })).toBeTruthy()
  fireEvent.click(screen.getByRole("button", { name: "View these payments" }))
  expect(screen.getByText("Receipts and subsequent payments: a,b")).toBeTruthy()
})

it("says so when the panels fail, and never draws them from an incomplete answer", () => {
  state.panels = "error"
  const { unmount } = render(
    <MemoryRouter>
      <InvestigatorOverview caseId="case" />
    </MemoryRouter>
  )
  expect(screen.getByRole("alert").textContent).toContain("The payments could not be loaded.")
  expect(screen.getByRole("button", { name: "Load payments again" })).toBeTruthy()
  expect(screen.queryByText("Imported payments in the selected accounts and dates")).toBeNull()
  unmount()
  state.panels = "ready"
  panels.complete = false
  try {
    render(
      <MemoryRouter>
        <InvestigatorOverview caseId="case" />
      </MemoryRouter>
    )
    expect(screen.getByRole("alert").textContent).toContain("Not all payments were returned.")
    expect(screen.queryByText(/Connections over/)).toBeNull()
  } finally {
    panels.complete = true
  }
})

it("never shows 0 while the totals load, and says so when they fail", () => {
  state.totals = "pending"
  const { unmount } = render(
    <MemoryRouter>
      <InvestigatorOverview caseId="case" />
    </MemoryRouter>
  )
  let progress = screen.getByRole("list", { name: "Your progress on this case" })
  expect(progress.textContent).toContain("Counting payments…")
  expect(progress.textContent).not.toContain("0 payments")
  expect(screen.getByText("Adding up payments…")).toBeTruthy()
  expect(screen.queryByText("Every payment has a category")).toBeNull()
  expect(screen.getByText("Counting accounts with payments in this scope…")).toBeTruthy()
  unmount()
  state.totals = "error"
  render(
    <MemoryRouter>
      <InvestigatorOverview caseId="case" />
    </MemoryRouter>
  )
  progress = screen.getByRole("list", { name: "Your progress on this case" })
  expect(progress.textContent).toContain("Payments could not be counted")
  expect(screen.getByRole("alert").textContent).toContain("Payments could not be added up")
  expect(screen.queryByText("Every payment has a category")).toBeNull()
})
