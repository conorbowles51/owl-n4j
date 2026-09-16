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
} from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { LedgerRowBrowser } from "./LedgerRowBrowser"
import type { LedgerTransaction } from "../api"
function render(children: ReactNode) {
  const client = new QueryClient()
  return originalRender(children, {
    wrapper: ({ children }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  })
}
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
it("refuses amount ordering across currencies and searches recorded references", () => {
  render(
    <LedgerRowBrowser
      transactions={[
        row("one", { bank_reference: "Invoice 123" }),
        row("two", { currency: "USD" }),
      ]}
    />
  )
  expect(
    screen.getByRole("option", { name: "Largest amount first (one currency)" })
  ).toBeDisabled()
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

vi.mock("./LedgerExportButton", () => ({ LedgerExportButton: () => null }))
vi.mock("./SavePaymentSelection", () => ({ SavePaymentSelection: () => null }))
const user = (id: string) =>
  ({ id, username: id }) as NonNullable<
    ReturnType<typeof useAuthStore.getState>["user"]
  >
beforeEach(() => {
  useFinancialDraftStore.setState({ drafts: {} })
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
