import "@/styles/globals.css"
import "../financial-workspace.css"
import { useState } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { WorkspaceScope } from "./InvestigationWorkspaceParts"
import { LedgerPanel } from "./LedgerPanel"
import {
  useInvestigationScope,
  useInvestigationScopeStore,
} from "../stores/investigation-scope"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import type { LedgerTransaction } from "../api"

const requests: URLSearchParams[] = []
let currencyScopeFixture = false
const caseId = "date-scope-case"
const transactions: LedgerTransaction[] = [
  "2021-01-03",
  "2021-01-31",
  "2021-02-01",
  "2021-02-28",
  "2020-12-31",
  "2021-01-15",
].map((date, index) => ({
  ...paymentFixture,
  case_id: caseId,
  key: `matching-${index}`,
  ref_id: `DATE-${index}`,
  ordering_date: date,
  transaction_date: date,
  description: `Transfer ${date}`,
  amount_minor: "10000",
  currency: "MXN",
  category: "Transfers",
  account_id: "account-a",
  account_institution: "Bank A",
  account_holder: "Example Company",
  account_label: "Bank A · 001",
}))
transactions.push(
  {
    ...transactions[0],
    key: "fees",
    description: "Account fee",
    category: "Fees",
  },
  {
    ...transactions[0],
    key: "other-account",
    description: "Other account transfer",
    account_id: "account-b",
    account_label: "Bank A · 002",
  },
  {
    ...transactions[0],
    key: "other-bank",
    description: "Other bank transfer",
    account_id: "account-c",
    account_institution: "Bank B",
    account_label: "Bank B · 003",
  },
  {
    ...transactions[0],
    key: "usd",
    description: "USD transfer",
    account_id: "account-d",
    account_label: "Bank A · 004",
    currency: "USD",
  }
)
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(async (url: string) => {
    const params = new URL(url, "http://synthetic.test").searchParams
    if (url.startsWith("/api/financial/ledger?")) {
      requests.push(params)
      const start = params.get("start_date"),
        end = params.get("end_date")
      const sourceRows = currencyScopeFixture
        ? transactions.map((row) =>
            row.ordering_date.startsWith("2021-02")
              ? { ...row, currency: "EUR" }
              : row
          )
        : transactions
      const matches = sourceRows.filter(
        (row) =>
          (!start || row.ordering_date >= start) &&
          (!end || row.ordering_date <= end)
      )
      return { case_id: caseId, transactions: matches, total: matches.length }
    }
    if (url.startsWith("/api/financial/ledger-accounts?"))
      return {
        case_id: caseId,
        has_more: false,
        items: [
          ["account-a", "Bank A", "001", "MXN"],
          ["account-b", "Bank A", "002", "MXN"],
          ["account-c", "Bank B", "003", "MXN"],
          ["account-d", "Bank A", "004", "USD"],
        ].map(([id, institution, identifier, currency]) => ({
          id,
          institution,
          identifier,
          currency,
          holder: "Example Company",
          display_label: `${institution} ${identifier}`,
        })),
      }
    return {
      case_id: caseId,
      categories: ["Transfers", "Fees"],
      entries: [],
      trails: [],
    }
  }),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))

function Workspace() {
  const [visible, setVisible] = useState(true)
  const [params] = useInvestigationScope(caseId)
  return (
    <main className="financial-workspace bg-background p-5 text-foreground">
      <button onClick={() => setVisible(!visible)}>
        {visible ? "Go to findings" : "Return to transactions"}
      </button>
      {visible ? (
        <>
          <WorkspaceScope caseId={caseId} datesOnly />
          <LedgerPanel caseId={caseId} params={params} investigation />
        </>
      ) : (
        <h1>Findings</h1>
      )}
    </main>
  )
}
afterEach(() => {
  cleanup()
  useInvestigationScopeStore.getState().reset()
  useFinancialDraftStore.setState({ drafts: {} })
  requests.length = 0
  currencyScopeFixture = false
})

it("shows the retained currency when a new date scope contains only EUR and clears it without losing the dates", async () => {
  currencyScopeFixture = true
  await page.viewport(1280, 900)
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <Workspace />
      </MemoryRouter>
    </QueryClientProvider>
  )
  await screen.findByText("10 of 10 imported transactions")
  await page.getByText("Filters", { exact: true }).click()
  await page
    .getByRole("combobox", { name: "Currency", exact: true })
    .selectOptions("USD")
  await page.getByText(/^Date range/).click()
  await page
    .getByLabelText("Transactions from", { exact: true })
    .fill("2021-02-01")
  await page
    .getByLabelText("Transactions to", { exact: true })
    .fill("2021-02-28")
  await page.getByRole("button", { name: "Apply", exact: true }).click()
  await screen.findByText("0 of 2 imported transactions")
  expect(screen.getByLabelText("Currency")).toHaveValue("USD")
  expect(
    screen.getByRole("option", {
      name: "USD · not in current account/date scope",
    })
  ).toBeInTheDocument()
  await page
    .getByRole("button", { name: "Go to findings", exact: true })
    .click()
  await page
    .getByRole("button", { name: "Return to transactions", exact: true })
    .click()
  await screen.findByText("0 of 2 imported transactions")
  expect(screen.getByLabelText("Currency")).toHaveValue("USD")
  await page.getByText("Filters (1)", { exact: true }).click()
  await page
    .getByRole("button", { name: "Clear payment filters", exact: true })
    .click()
  await screen.findByText("2 of 2 imported transactions")
  expect(
    screen.getByRole("region", { name: "Payments matching your filters" })
  ).toHaveTextContent("Currencies: EUR")
  expect(screen.getByText(/^Date range/)).toHaveTextContent(
    "2021-02-01 to 2021-02-28"
  )
  expect(screen.getByLabelText("Currency")).toHaveValue("")
})

it("applies native date inputs alongside bank, account, category and currency, retains them on return, and clears only dates", async () => {
  await page.viewport(1440, 1000)
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <Workspace />
      </MemoryRouter>
    </QueryClientProvider>
  )
  await screen.findByText("10 of 10 imported transactions")
  fireEvent.click(
    screen.getByLabelText("Bank filter").querySelector("summary")!
  )
  await act(async () => {
    await page.getByRole("checkbox", { name: "Bank A", exact: true }).click()
  })
  fireEvent.click(
    screen.getByLabelText("Bank account filter").querySelector("summary")!
  )
  await act(async () => {
    await page
      .getByRole("checkbox", {
        name: "Bank A · 001 · Example Company · MXN",
        exact: true,
      })
      .click()
  })
  await act(async () => {
    await page
      .getByRole("combobox", { name: "Filter financial payments by category" })
      .selectOptions("Transfers")
  })
  fireEvent.click(screen.getByText("Filters (1)", { exact: true }))
  await act(async () => {
    await page
      .getByRole("combobox", { name: "Currency", exact: true })
      .selectOptions("MXN")
  })
  expect(screen.getByText("6 of 10 imported transactions")).toBeVisible()
  fireEvent.click(screen.getByText(/^Date range/))
  await act(async () => {
    await page
      .getByLabelText("Transactions from", { exact: true })
      .fill("2021-01-01")
  })
  expect(screen.getByLabelText("Transactions from")).toHaveValue("2021-01-01")
  await act(async () => {
    await page
      .getByLabelText("Transactions to", { exact: true })
      .fill("2021-01-31")
  })
  expect(screen.getByLabelText("Transactions from")).toHaveValue("2021-01-01")
  expect(screen.getByLabelText("Transactions to")).toHaveValue("2021-01-31")
  await act(async () => {
    await page.getByRole("button", { name: "Apply", exact: true }).click()
  })
  await waitFor(() =>
    expect(screen.getByText("3 of 7 imported transactions")).toBeVisible()
  )
  expect(requests.at(-1)?.get("start_date")).toBe("2021-01-01")
  expect(requests.at(-1)?.get("end_date")).toBe("2021-01-31")
  expect(screen.getByLabelText("Transactions from")).toHaveValue("2021-01-01")
  expect(screen.getByLabelText("Transactions to")).toHaveValue("2021-01-31")
  expect(screen.getByTestId("ledger-filter-scope")).toHaveTextContent(
    "From 2021-01-01, inclusive. To 2021-01-31, inclusive."
  )
  const table = screen.getByRole("table", {
    name: "Investigation transactions",
  })
  expect(table).toHaveTextContent("Transfer 2021-01-31")
  expect(table).not.toHaveTextContent("2021-02")
  expect(table.querySelectorAll("tbody tr")).toHaveLength(3)
  expect(screen.getByRole("button", { name: "Download CSV (3)" })).toBeVisible()
  await act(async () => {
    await page.getByRole("button", { name: "Go to findings" }).click()
    await page.getByRole("button", { name: "Return to transactions" }).click()
  })
  await screen.findByText("3 of 7 imported transactions")
  expect(screen.getByText(/^Date range/)).toHaveTextContent(
    "2021-01-01 to 2021-01-31"
  )
  fireEvent.click(screen.getByText(/^Date range/))
  expect(screen.getByLabelText("Transactions from")).toHaveValue("2021-01-01")
  expect(screen.getByLabelText("Transactions to")).toHaveValue("2021-01-31")
  expect(
    screen.getByRole("combobox", {
      name: "Filter financial payments by category",
    })
  ).toHaveValue("Transfers")
  expect(
    screen.getByRole("combobox", { name: "Currency", hidden: true })
  ).toHaveValue("MXN")
  await act(async () => {
    await page.getByRole("button", { name: "Reset", exact: true }).click()
  })
  await screen.findByText("6 of 10 imported transactions")
  expect(screen.getByLabelText("Transactions from")).toHaveValue("")
  expect(screen.getByLabelText("Transactions to")).toHaveValue("")
  expect(
    screen.getByRole("combobox", {
      name: "Filter financial payments by category",
    })
  ).toHaveValue("Transfers")
  fireEvent.click(
    screen.getByLabelText("Bank filter").querySelector("summary")!
  )
  expect(
    within(screen.getByLabelText("Bank filter")).getByRole("checkbox", {
      name: "Bank A",
    })
  ).toBeChecked()
  fireEvent.click(
    screen.getByLabelText("Bank account filter").querySelector("summary")!
  )
  expect(
    within(screen.getByLabelText("Bank account filter")).getByRole("checkbox", {
      name: "Bank A · 001 · Example Company · MXN",
    })
  ).toBeChecked()
})
