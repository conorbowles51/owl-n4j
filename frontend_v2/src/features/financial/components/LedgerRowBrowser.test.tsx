import { useInvestigationScopeStore } from "../stores/investigation-scope"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import {
  paymentTableDraftName,
  resetPaymentTableView,
} from "../lib/payment-table-draft"
import {
  act,
  render as originalRender,
  screen,
  fireEvent,
  within,
} from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { LedgerRowBrowser } from "./LedgerRowBrowser"
import type { LedgerTransaction } from "../api"
import { RowJudgements } from "../hooks/use-judgement-rows"
import type { Judgement } from "../lib/judgements"
function render(children: ReactNode) {
  const client = new QueryClient()
  return originalRender(children, {
    wrapper: ({ children }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  })
}
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(async (url: string) => ({
    case_id: new URL(url, "http://test").searchParams.get("case_id"),
    items: [],
    has_more: false,
    total: 0,
    entries: [],
    categories: [],
  })),
}))
vi.mock("./LedgerTable", () => ({
  LedgerTable: ({
    transactions,
    onSource,
  }: {
    transactions: LedgerTransaction[]
    onSource: (r: LedgerTransaction) => void
  }) => (
    <ul>
      {transactions.map((r) => (
        <li key={r.key}>
          <button onClick={() => onSource?.(r)}>{r.key}</button>
        </li>
      ))}
    </ul>
  ),
}))
function row(
  key: string,
  overrides: Partial<LedgerTransaction> = {}
): LedgerTransaction {
  return {
    key,
    currency: "GBP",
    amount_minor: "9007199254740993",
    description: "Payment",
    direction: "debit",
    proof_class: "p3",
    ordering_date: "2026-01-01",
    ...overrides,
  } as LedgerTransaction
}
it("sorts exact amounts and passes the original selected row to source actions", () => {
  const first = row("larger"),
    second = row("smaller", { amount_minor: "9007199254740992" }),
    source = vi.fn()
  render(<LedgerRowBrowser transactions={[first, second]} onSource={source} />)
  fireEvent.change(screen.getByLabelText("Sort payments"), {
    target: { value: "amount-asc" },
  })
  expect(screen.getAllByRole("listitem").map((r) => r.textContent)).toEqual([
    "smaller",
    "larger",
  ])
  fireEvent.click(screen.getByRole("button", { name: "smaller" }))
  expect(source).toHaveBeenCalledWith(second)
})
it("allows amount ordering across currencies and searches recorded references", () => {
  render(
    <LedgerRowBrowser
      transactions={[
        row("one", { bank_reference: "Invoice 123" }),
        row("two", { currency: "USD" }),
      ]}
    />
  )
  expect(
    screen.getByRole("option", { name: "Largest amount first" })
  ).not.toBeDisabled()
  fireEvent.change(screen.getByLabelText("Search payments"), {
    target: { value: "invoice 123" },
  })
  expect(screen.getByText(/1 payments match your filters/)).toBeInTheDocument()
  expect(screen.queryByRole("button", { name: "two" })).not.toBeInTheDocument()
})
it("pages the complete loaded set and resets its page after filtering", () => {
  render(
    <LedgerRowBrowser
      transactions={Array.from({ length: 51 }, (_, i) => row(String(i)))}
    />
  )
  expect(screen.getAllByRole("listitem")).toHaveLength(50)
  fireEvent.click(screen.getByRole("button", { name: "Next ledger rows" }))
  expect(screen.getAllByRole("listitem")).toHaveLength(1)
  fireEvent.change(screen.getByLabelText("Search payments"), {
    target: { value: "missing" },
  })
  expect(screen.getByText(/No payments match/)).toBeInTheDocument()
})

it("filters inclusive exact ranges, rejects invalid precision and resets on currency change", () => {
  render(
    <LedgerRowBrowser
      transactions={[
        row("larger"),
        row("smaller", { amount_minor: "9007199254740992" }),
      ]}
    />
  )
  expect(screen.getByLabelText("Table minimum amount")).toBeDisabled()
  fireEvent.change(screen.getByLabelText("Currency"), {
    target: { value: "GBP" },
  })
  fireEvent.change(screen.getByLabelText("Table minimum amount"), {
    target: { value: "90071992547409.93" },
  })
  fireEvent.change(screen.getByLabelText("Table maximum amount"), {
    target: { value: "90071992547409.93" },
  })
  expect(screen.getByRole("button", { name: "larger" })).toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "smaller" })
  ).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText("Table maximum amount"), {
    target: { value: "1.001" },
  })
  expect(screen.getByRole("alert")).toHaveTextContent("valid amounts")
  expect(
    screen.queryByRole("button", { name: "larger" })
  ).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText("Currency"), {
    target: { value: "" },
  })
  expect(screen.getByLabelText("Table minimum amount")).toHaveValue("")
  expect(screen.getByRole("button", { name: "smaller" })).toBeInTheDocument()
})

it("keeps a retained currency filter visible when account or date scope no longer contains that currency", () => {
  const eur = row("EUR payment", { currency: "EUR" })
  const view = render(
    <LedgerRowBrowser
      transactions={[row("USD payment", { currency: "USD" }), eur]}
    />
  )
  fireEvent.change(screen.getByLabelText("Currency"), {
    target: { value: "USD" },
  })
  view.rerender(<LedgerRowBrowser transactions={[eur]} />)
  expect(screen.getByLabelText("Currency")).toHaveValue("USD")
  expect(
    screen.getByRole("option", {
      name: /USD.*not in current account\/date scope/,
    })
  ).toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "EUR payment" })
  ).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Clear payment filters" }))
  expect(screen.getByLabelText("Currency")).toHaveValue("")
  expect(
    screen.getByRole("button", { name: "EUR payment" })
  ).toBeInTheDocument()
})

vi.mock("./LedgerExportButton", () => ({
  LedgerExportButton: ({
    tableView,
    params,
  }: {
    tableView?: unknown
    params?: unknown
  }) => (
    <output data-testid="export-filters">
      {JSON.stringify({ ...(tableView as object), ...(params as object) })}
    </output>
  ),
}))
vi.mock("./SavePaymentSelection", () => ({ SavePaymentSelection: () => null }))
const user = (id: string) =>
  ({ id, username: id }) as NonNullable<
    ReturnType<typeof useAuthStore.getState>["user"]
  >
beforeEach(() => {
  // These tests read the dense table; the card rows have their own test below.
  localStorage.setItem("financial-transactions-table-view", "1")
  useFinancialDraftStore.setState({ drafts: {} })
  useInvestigationScopeStore.getState().reset()
  useAuthStore.setState({ user: user("reviewer-a") })
})

it("restores every payment filter and the table page after leaving and reopening the case", () => {
  const rows = Array.from({ length: 70 }, (_, i) =>
    row(String(i), { amount_minor: "10000" })
  )
  const show = () => (
    <LedgerRowBrowser
      transactions={rows}
      exportContext={{ caseId: "case-a", params: {} }}
    />
  )
  const first = render(show())
  for (const [name, value] of [
    ["Search payments", "Payment"],
    ["Currency", "GBP"],
    ["Table minimum amount", "50"],
    ["Table maximum amount", "150"],
    ["Money in or out", "debit"],
    ["Table proof class", "p3"],
    ["Sort payments", "newest"],
  ])
    fireEvent.change(screen.getByLabelText(name), { target: { value } })
  fireEvent.click(screen.getByRole("button", { name: "Next ledger rows" }))
  expect(screen.getAllByRole("listitem")).toHaveLength(20)
  first.unmount()
  render(show())
  for (const [name, value] of [
    ["Search payments", "Payment"],
    ["Currency", "GBP"],
    ["Table minimum amount", "50"],
    ["Table maximum amount", "150"],
    ["Money in or out", "debit"],
    ["Table proof class", "p3"],
    ["Sort payments", "newest"],
  ])
    expect(screen.getByLabelText(name)).toHaveValue(value)
  expect(screen.getByText("51–70 of 70 matching rows")).toBeVisible()
  expect(screen.getAllByRole("listitem")).toHaveLength(20)
})

it("keeps table views separate by case, account/date scope and signed-in user", () => {
  const rows = [row("one")]
  const show = (caseId = "case-a", accountId?: string) => (
    <LedgerRowBrowser
      transactions={rows}
      exportContext={{ caseId, params: { accountId } }}
    />
  )
  const view = render(show())
  fireEvent.change(screen.getByLabelText("Search payments"), {
    target: { value: "Payment" },
  })
  view.rerender(show("case-b"))
  expect(screen.getByLabelText("Search payments")).toHaveValue("")
  view.rerender(show("case-a", "account-b"))
  expect(screen.getByLabelText("Search payments")).toHaveValue("")
  view.rerender(show())
  expect(screen.getByLabelText("Search payments")).toHaveValue("Payment")
  act(() => useAuthStore.setState({ user: user("reviewer-b") }))
  view.rerender(show())
  expect(screen.getByLabelText("Search payments")).toHaveValue("")
})

it("clears the saved table filters so reopening does not restore the old search", () => {
  const show = () => (
    <LedgerRowBrowser
      transactions={[row("one")]}
      exportContext={{ caseId: "case-a", params: {} }}
    />
  )
  const view = render(show())
  fireEvent.change(screen.getByLabelText("Search payments"), {
    target: { value: "missing" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Clear payment filters" }))
  view.unmount()
  render(show())
  expect(screen.getByLabelText("Search payments")).toHaveValue("")
  expect(screen.getByRole("button", { name: "one" })).toBeVisible()
})

it("opens a named statement with fresh table filters and preserves other views and selected payments", () => {
  useAuthStore.setState({ user: null })
  const params = { accountId: "checking" }
  useFinancialDraftStore
    .getState()
    .put(`anonymous:case:${paymentTableDraftName(params, true)}`, {
      search: "old search",
      currency: "EUR",
      page: 2,
    })
  useFinancialDraftStore
    .getState()
    .put("anonymous:case:selected-payments", ["earlier"])
  useFinancialDraftStore
    .getState()
    .put("anonymous:other-case:some-note", "Keep another case")
  resetPaymentTableView("case", params, {
    source_document_id: "source-a",
    filename: "Checking.pdf",
  })
  const mounted = render(
    <LedgerRowBrowser
      investigation
      exportContext={{ caseId: "case", params }}
      transactions={[
        row("a", { source_document_id: "source-a", currency: "USD" }),
        row("b", { source_document_id: "source-b", currency: "USD" }),
      ]}
    />
  )
  expect(screen.getByLabelText("Search payments")).toHaveValue("")
  expect(screen.getByLabelText("Currency")).toHaveValue("")
  expect(
    screen.getByRole("region", { name: "Selected statement transactions" })
  ).toHaveTextContent("Checking.pdf")
  expect(
    screen
      .getByRole("table", { name: "Investigation transactions" })
      .querySelectorAll("tbody tr")
  ).toHaveLength(1)
  expect(
    useFinancialDraftStore.getState().drafts["anonymous:case:selected-payments"]
  ).toEqual(["earlier"])
  expect(
    useFinancialDraftStore.getState().drafts["anonymous:other-case:some-note"]
  ).toBe("Keep another case")
  fireEvent.click(
    screen.getByRole("button", { name: "Clear statement filter" })
  )
  expect(
    screen
      .getByRole("table", { name: "Investigation transactions" })
      .querySelectorAll("tbody tr")
  ).toHaveLength(2)
  mounted.unmount()
  expect(
    useFinancialDraftStore.getState().drafts[
      `anonymous:case:${paymentTableDraftName(params, true)}`
    ]
  ).toMatchObject({ sourceDocumentId: "" })
})

it("selects every matching payment above the old limit while showing only one table page", () => {
  const rows = Array.from({ length: 2700 }, (_, i) => row(String(i)))
  render(
    <LedgerRowBrowser
      transactions={rows}
      investigation
      exportContext={{ caseId: "large", params: {} }}
    />
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Select all 2700 matching payments" })
  )
  expect(
    useFinancialDraftStore.getState().drafts[
      "reviewer-a:large:selected-payments"
    ]
  ).toEqual(rows.map((row) => row.key))
  expect(screen.getAllByRole("checkbox")).toHaveLength(50)
  fireEvent.click(screen.getByRole("button", { name: "Next ledger rows" }))
  expect(
    screen
      .getAllByRole("checkbox")
      .every((input) => (input as HTMLInputElement).checked)
  ).toBe(true)
})

it("shows only the imported batch sources and lets the investigator clear that scope", () => {
  const params = { startDate: "2020-01-01", endDate: "2026-12-31" }
  resetPaymentTableView("case", params, {
    batch_id: "batch",
    revision: "a".repeat(64),
    source_document_ids: ["source-a", "source-b"],
    statement_count: 2,
  })
  render(
    <LedgerRowBrowser
      investigation
      exportContext={{ caseId: "case", params }}
      transactions={[
        row("a", { source_document_id: "source-a" }),
        row("b", { source_document_id: "source-b" }),
        row("c", { source_document_id: "unrelated" }),
      ]}
    />
  )
  expect(
    screen.getByRole("region", { name: "Imported batch transactions" })
  ).toHaveTextContent("2 imported statements")
  expect(
    screen
      .getByRole("table", { name: "Investigation transactions" })
      .querySelectorAll("tbody tr")
  ).toHaveLength(2)
  expect(
    screen.getByRole("link", { name: "Open import batch" })
  ).toHaveAttribute("href", "/cases/case/financial?view=statements&batch=batch")
  fireEvent.click(screen.getByRole("button", { name: "Clear batch filter" }))
  expect(
    screen
      .getByRole("table", { name: "Investigation transactions" })
      .querySelectorAll("tbody tr")
  ).toHaveLength(3)
  expect(
    screen.queryByRole("region", { name: "Imported batch transactions" })
  ).not.toBeInTheDocument()
})

it("loads every account then filters one holder across banks, preserving pagination, totals and export scope", () => {
  const transactions = Array.from({ length: 125 }, (_, index) =>
    row(`row-${index}`, {
      case_id: "case",
      account_id: index < 60 ? "a" : index < 120 ? "b" : "c",
      account_label:
        index < 60
          ? "Example Company · Bank A · 001"
          : index < 120
            ? "Example Company · Bank B · 002"
            : "Other Company · Bank A · 003",
      account_holder:
        index < 60
          ? "Example Company"
          : index < 120
            ? " EXAMPLE  COMPANY "
            : "Other Company",
      amount_minor: "100",
      currency: "USD",
      description: `Payment ${index}`,
    })
  )
  render(
    <LedgerRowBrowser
      investigation
      transactions={transactions}
      exportContext={{ caseId: "case", params: {} }}
    />
  )
  const tableRows = () =>
    screen
      .getByRole("table", { name: "Investigation transactions" })
      .querySelectorAll("tbody tr")
  expect(tableRows()).toHaveLength(50)
  expect(screen.getByText("1–50 of 125 matching rows")).toBeVisible()
  act(() =>
    useInvestigationScopeStore
      .getState()
      .apply("case", { accountHolders: ["example company"] })
  )
  expect(screen.getByText("1–50 of 120 matching rows")).toBeVisible()
  expect(screen.getByText("120.00 USD")).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Next ledger rows" }))
  expect(screen.getByText("51–100 of 120 matching rows")).toBeVisible()
  act(() =>
    useInvestigationScopeStore
      .getState()
      .apply("case", { accountHolders: ["example company"], accountIds: ["b"] })
  )
  expect(screen.getByText("51–60 of 60 matching rows")).toBeVisible()
  expect(screen.getByText("60.00 USD")).toBeVisible()
  expect(
    JSON.parse(screen.getByTestId("export-filters").textContent!)
  ).toMatchObject({ accountIds: ["b"], accountHolders: ["example company"] })
  act(() =>
    useInvestigationScopeStore.getState().apply("case", {
      accountHolders: ["example company", "other company"],
      accountIds: ["b", "c"],
    })
  )
  expect(screen.getByText("51–65 of 65 matching rows")).toBeVisible()
  act(() => useInvestigationScopeStore.getState().apply("case", {}))
  expect(screen.getByText("51–100 of 125 matching rows")).toBeVisible()
})

it("shows roomy cards by default with totals and category tiles that filter, and remembers Table view", () => {
  localStorage.removeItem("financial-transactions-table-view")
  render(
    <LedgerRowBrowser
      investigation
      exportContext={{ caseId: "case", params: {} }}
      transactions={[
        row("rent", { category: "Rent and leases", amount_minor: "50000", ordering_date: "2026-01-03" }),
        row("fee", { category: "Bank fees", amount_minor: "200", ordering_date: "2026-03-04" }),
        row("pay", { direction: "credit", amount_minor: "90000", ordering_date: "2026-03-05", description: "Salary" }),
      ]}
    />
  )
  const list = screen.getByRole("list", { name: "Investigation transactions" })
  expect(within(list).getAllByRole("checkbox")).toHaveLength(3)
  expect(screen.queryByRole("table", { name: "Investigation transactions" })).not.toBeInTheDocument()
  const glance = screen.getByRole("region", { name: "This view at a glance" })
  expect(glance).toHaveTextContent("+900")
  expect(glance).toHaveTextContent("−502")
  // February had no payments read: shown as a gap, never skipped.
  expect(within(glance).getByTitle("2026-02: no payments read")).toBeInTheDocument()
  const where = screen.getByRole("region", { name: "Where the money went" })
  expect(within(where).getByText(/Needs a category · 1/)).toBeInTheDocument()
  fireEvent.click(within(where).getByRole("button", { name: /^Rent and leases · 1/ }))
  expect(within(list).getAllByRole("checkbox")).toHaveLength(1)
  fireEvent.click(within(where).getByRole("button", { name: /^Rent and leases · 1/ }))
  expect(within(list).getAllByRole("checkbox")).toHaveLength(3)
  fireEvent.click(screen.getByRole("button", { name: "Table view" }))
  expect(screen.getByRole("table", { name: "Investigation transactions" })).toBeInTheDocument()
  expect(localStorage.getItem("financial-transactions-table-view")).toBe("1")
})

it("shows every set filter as a removable chip and removing one clears only it", () => {
  render(
    <LedgerRowBrowser
      investigation
      exportContext={{ caseId: "chips-case", params: {} }}
      transactions={[
        row("in", { direction: "credit", case_id: "chips-case" }),
        row("out", { case_id: "chips-case" }),
      ]}
    />
  )
  expect(screen.queryByRole("group", { name: "Active filters" })).toBeNull()
  fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "GBP" } })
  fireEvent.change(screen.getByLabelText("Money in or out"), { target: { value: "credit" } })
  fireEvent.change(screen.getByLabelText("Search payments"), { target: { value: "Payment" } })
  const chips = screen.getByRole("group", { name: "Active filters" })
  expect(within(chips).getByText("3 active")).toBeInTheDocument()
  fireEvent.click(within(chips).getByRole("button", { name: "Remove filter Incoming" }))
  expect(screen.getByLabelText("Money in or out")).toHaveValue("")
  expect(screen.getByLabelText("Currency")).toHaveValue("GBP")
  expect(within(screen.getByRole("group", { name: "Active filters" })).getByText("2 active")).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Remove filter GBP" }))
  expect(screen.getByLabelText("Currency")).toHaveValue("")
})

vi.mock("./PaymentNamingPanel", () => ({
  PaymentNamingPanel: ({ currentId, readOnly }: { currentId: string; readOnly?: boolean }) => (
    <aside aria-label="naming panel">
      {currentId} {readOnly ? "read-only" : "editable"}
    </aside>
  ),
}))

it("opens a viewer the statement line of a payment without a name instead of filtering by the reason", () => {
  localStorage.removeItem("financial-transactions-table-view")
  const reason = "Cheque deposit — the statement doesn’t name who wrote the cheque"
  render(
    <LedgerRowBrowser
      investigation
      exportContext={{ caseId: "case", params: {} }}
      transactions={[
        row("cheque", {
          direction: "credit",
          from_name: "",
          to_name: "HOLDER",
          label_sources: { from_name: { source: "missing", reason, explanation: reason } },
        } as Partial<LedgerTransaction>),
        row("other", { direction: "credit", from_name: "", to_name: "HOLDER" }),
      ]}
    />
  )
  const list = screen.getByRole("list", { name: "Investigation transactions" })
  fireEvent.click(within(list).getAllByRole("button", { name: /See the line who paid/ })[0])
  expect(screen.getByRole("complementary", { name: "naming panel" })).toHaveTextContent("cheque read-only")
  // The table is not narrowed to the reason as if it were a party.
  expect(within(list).getAllByRole("checkbox")).toHaveLength(2)
  expect(screen.getByRole("button", { name: "See their statement lines one by one" })).toBeInTheDocument()
})
it("lists payments with judgement calls focus first and filters them by priority", () => {
  const call = (priority: number, strength = "proved") =>
    ({ id: `j${priority}${strength}`, priority, strength, category: "x", origin: "processor", status: "open" }) as unknown as Judgement
  const calls: Record<string, Judgement[]> = {
    describe: [call(3)],
    money: [call(1)],
    account: [call(2, "inferred")],
  }
  render(
    <RowJudgements.Provider value={{ caseId: "case-1", lookup: (r) => calls[r.key] || [] }}>
      <LedgerRowBrowser
        transactions={[row("describe"), row("plain"), row("account"), row("money")]}
      />
    </RowJudgements.Provider>
  )
  fireEvent.change(screen.getByLabelText("Judgement calls"), { target: { value: "any" } })
  expect(screen.getAllByRole("listitem").map((r) => r.textContent)).toEqual(["money", "account", "describe"])
  const legend = screen.getByRole("group", { name: "Priority" })
  expect(legend).toHaveTextContent("Check first (1)")
  fireEvent.click(within(legend).getByRole("button", { name: /Check soon/ }))
  expect(screen.getAllByRole("listitem").map((r) => r.textContent)).toEqual(["account"])
})
