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
  register: "ready" as "ready" | "pending" | "error",
  findings: "ready" as "ready" | "pending" | "error",
  calls: "ready" as "ready" | "pending" | "error",
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
    data: state.totals === "ready" ? { ...totals, uncategorised: state.uncategorised } : undefined,
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
    files: {
      data: state.register === "ready" ? [{ id: "f1" }, { id: "f2" }] : undefined,
      isPending: state.register === "pending",
      isError: state.register === "error",
    },
    imports: {
      data:
        state.register === "ready"
          ? state.registerDone
            ? { truncated: false, files: ["f1", "f2"].map((id) => ({ evidence_file_id: id, current_transactions: 3, periods: [{}], available_periods: 0, periods_with_checks: 0 })) }
            : { truncated: false, files: [{ evidence_file_id: "f1", current_transactions: 3, periods: [{}], available_periods: 0, periods_with_checks: 2 }] }
          : undefined,
      isPending: state.register === "pending",
      isError: state.register === "error",
    },
  }),
}))
vi.mock("@/features/workspace/hooks/use-casework", () => ({
  useCaseworkEntries: () => ({
    isPending: state.findings === "pending",
    isError: state.findings === "error",
    isSuccess: state.findings === "ready",
    data: state.findings === "ready" ? { entries: [], total: 0 } : undefined,
  }),
}))
vi.mock("../hooks/use-judgements", () => ({
  useJudgementCounts: () => ({
    isSuccess: state.calls === "ready",
    isError: state.calls === "error",
    data: state.calls === "ready" ? { case: { total: 9, open: state.openCalls, inferred: 4 } } : undefined,
  }),
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
  state.register = "ready"
  state.findings = "ready"
  state.calls = "ready"
  state.openCalls = 7
  state.uncategorised = 1
  state.registerDone = false
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

it.each([
  ["pending", "Checking statement files…"],
  ["error", "Statement status could not be loaded"],
] as const)("never shows 0 files or 0 saved while the statement files are %s", (register, says) => {
  state.register = register
  render(
    <MemoryRouter>
      <InvestigatorOverview caseId="case" />
    </MemoryRouter>
  )
  const progress = screen.getByRole("list", { name: "Your progress on this case" })
  expect(progress.textContent).not.toMatch(/\b0 (file|saved)/)
  expect(progress.textContent).toMatch(new RegExp(`Load\\([a-z ]+\\)${says}`))
  expect(progress.textContent).toMatch(new RegExp(`Read\\([a-z ]+\\)${says}`))
  expect(screen.getByRole("heading", { name: /Your case at a glance/ }).textContent).toContain(says)
})

it.each([
  ["calls", "pending", "Counting Loupe's calls…"],
  ["calls", "error", "Loupe's calls could not be counted."],
  ["findings", "pending", "Loading findings…"],
  ["findings", "error", "Findings could not be loaded."],
] as const)("says nothing about %s until they are counted (%s): the ledger is not called checked without the calls, and findings are not called none", (what, how, says) => {
  // Everything before them is done: files saved, nothing to check, every payment categorised.
  state.uncategorised = 0
  state.openCalls = 0
  state.registerDone = true
  state[what] = how
  render(
    <MemoryRouter>
      <InvestigatorOverview caseId="case" />
    </MemoryRouter>
  )
  const progress = screen.getByRole("list", { name: "Your progress on this case" })
  if (what === "calls") {
    // Whether the ledger is checked turns on Loupe's calls: not said until they are counted.
    expect(screen.queryByRole("heading", { name: /The ledger is checked/ })).toBeNull()
    expect(screen.getByRole("heading", { name: /Your case at a glance/ }).textContent).toContain(says)
  } else {
    // It does not turn on the findings: the title stays, and only the line about findings waits for them.
    const heading = screen.getByRole("heading", { name: /The ledger is checked/ })
    expect(heading.textContent).toContain(says)
    expect(heading.textContent).not.toContain("Follow the money and record")
    expect(progress.textContent).not.toContain("No findings yet")
  }
})

it("says the ledger is checked once the files, calls and findings are all counted and nothing is open", () => {
  state.uncategorised = 0
  state.openCalls = 0
  state.registerDone = true
  render(
    <MemoryRouter>
      <InvestigatorOverview caseId="case" />
    </MemoryRouter>
  )
  expect(screen.getByRole("heading", { name: /The ledger is checked/ })).toBeTruthy()
  expect(screen.getByRole("list", { name: "Your progress on this case" }).textContent).toContain("No findings yet")
})
