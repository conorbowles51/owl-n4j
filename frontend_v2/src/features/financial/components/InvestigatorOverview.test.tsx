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
const state = vi.hoisted(() => ({
  payments: "ready" as "ready" | "pending",
  totals: "ready" as "ready" | "pending" | "error",
}))
vi.mock("../hooks/use-investigator-payments", () => ({
  useInvestigatorPayments: () =>
    state.payments === "ready"
      ? { rows, complete: true, query: { isPending: false, isError: false, refetch: vi.fn() } }
      : { rows: [], complete: false, query: { isPending: true, isError: false, refetch: vi.fn() } },
}))
vi.mock("../hooks/use-ledger-overview", () => ({
  useLedgerOverview: () => ({
    data: state.totals === "ready" ? totals : undefined,
    isPending: state.totals === "pending",
    isError: state.totals === "error",
    isSuccess: state.totals === "ready",
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
vi.mock("./InvestigatorFollowMoney", () => ({ MoneyConnections: () => <p>Connections</p> }))
vi.mock("./OverviewStatementCoverage", () => ({ OverviewStatementCoverage: () => <p>Coverage grid</p> }))
vi.mock("./InvestigationWorkspaceParts", async (original) => ({
  ...(await original<typeof import("./InvestigationWorkspaceParts")>()),
  WorkspaceScope: () => <p>Scope</p>,
}))
vi.mock("./InvestigationTransactionTable", () => ({ PaymentTotals: ({ label }: { label: string }) => <p>{label}</p> }))
afterEach(() => {
  cleanup()
  state.payments = "ready"
  state.totals = "ready"
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
  for (const text of ["Scope", "Connections", "Coverage grid", "Imported payments in the selected accounts and dates", "Saved investigation work", "Your statements", "Explore activity over time"])
    expect(screen.getByText(text)).toBeTruthy()
  expect(screen.getByRole("button", { name: "Add or review statements" })).toBeTruthy()
  fireEvent.click(screen.getByRole("button", { name: "Check the 2 statements →" }))
  expect(useFinancialStore.getState().mainView).toBe("statements")
})

it("shows the top figures from the server's totals while every payment is still loading", () => {
  state.payments = "pending"
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
