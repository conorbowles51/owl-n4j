import "@/styles/globals.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { useState } from "react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { LedgerPanel } from "./LedgerPanel"
import { WorkspaceScope } from "./InvestigationWorkspaceParts"
import { useInvestigationScope, useInvestigationScopeStore } from "../stores/investigation-scope"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { paymentFixture } from "../lib/payment-fixture.test-support"

vi.mock("@/lib/api-client", async (original) => ({ ...(await original<typeof import("@/lib/api-client")>()), fetchAPI: vi.fn() }))
vi.mock("../hooks/use-financial-access", () => ({ useFinancialAccess: () => ({ canEdit: true }) }))
const caseId = "known-account-case"
const period = (id: string, currency: string, month = "01") => ({ id, source_document_id: `source-${id}`, start: `2026-${month}-01`, end: `2026-${month}-${month === "02" ? "28" : "31"}`, currency })
const accounts = [
  { id: "usd", holder: "Example Company", identifier: "0001", institution: "Example Bank", currency: "USD", account_type: "checking", statement_periods: [period("usd-jan", "USD")] },
  { id: "eur", holder: "Example Company", identifier: "0002", institution: "Example Bank", currency: "EUR", account_type: "checking", statement_periods: [period("eur-jan", "EUR")] },
  { id: "eur-alias", canonical_id: "eur", holder: null, identifier: null, institution: null, currency: null, account_type: null, statement_periods: [period("eur-jan", "EUR")] },
  { id: "card", holder: "Example Company", identifier: "0003", institution: "Card Bank", currency: "EUR", account_type: "credit_card", statement_periods: [period("card-feb", "EUR", "02")] },
  { id: "pending", holder: "Other Company", identifier: "0004", institution: "Pending Bank", currency: "GBP", account_type: "checking", statement_periods: [] },
  { id: "unknown", holder: "Other Company", identifier: "0005", institution: "Unknown Bank", currency: null, account_type: null, statement_periods: [] },
]
const rows = [
  { ...paymentFixture, key: "usd-credit", account_id: "usd", account_holder: "Example Company", account_label: "Example Bank · 0001", account_institution: "Example Bank", account_type: "checking", currency: "USD", ordering_date: "2026-01-03", amount_minor: "10000", direction: "credit" },
  { ...paymentFixture, key: "usd-debit", account_id: "usd", account_holder: "Example Company", account_label: "Example Bank · 0001", account_institution: "Example Bank", account_type: "checking", currency: "USD", ordering_date: "2026-01-04", amount_minor: "2500", direction: "debit" },
]
let client: QueryClient
const urls: string[] = []
beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  useFinancialDraftStore.setState({ drafts: {} })
  useInvestigationScopeStore.getState().reset()
  urls.length = 0
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method) throw Error("This known-account journey must not change case data.")
    urls.push(url)
    const params = new URL(url, "http://synthetic.test").searchParams
    if (url.includes("/ledger-accounts?")) {
      const offset = Number(params.get("offset") || 0)
      return { case_id: caseId, has_more: offset === 0, items: offset === 0 ? accounts.slice(0, 3) : accounts.slice(3) }
    }
    if (url.includes("/ledger?")) {
      const start = params.get("start_date"), end = params.get("end_date")
      const selected = params.getAll("account_ids")
      const matching = rows.filter((row) => (!start || row.ordering_date >= start) && (!end || row.ordering_date <= end) && (!selected.length || selected.includes(row.account_id)))
      return { case_id: caseId, total: matching.length, transactions: matching }
    }
    if (url.includes("/account-history?")) return { case_id: caseId, applied: false, groups: [{ key: "eur:EUR:asset", account_id: "eur", currency: "EUR", balance_kind: "asset", label: "Example Bank · 0002", periods: [{ ...period("eur-jan", "EUR"), evidence_file_id: null, filename: "Synthetic January.pdf", opening_minor: "5000", closing_minor: "5000", status: "confirmed_no_activity", assessment_current: true, transaction_count: 0, undated_count: 0, activity: [] }] }] }
    return { case_id: caseId, entries: [], total: 0, categories: [], trails: [], items: [], has_more: false }
  })
})
afterEach(() => { cleanup(); client.clear(); vi.resetAllMocks() })
function Workspace() {
  const [away, setAway] = useState(false)
  const [params] = useInvestigationScope(caseId)
  return <main className="p-4 space-y-3">
    <button onClick={() => setAway(!away)}>{away ? "Return to Transactions" : "Open Findings"}</button>
    {away ? <h1>Findings</h1> : <>
      <h1>Transactions</h1><WorkspaceScope caseId={caseId} datesOnly />
      <LedgerPanel caseId={caseId} params={params} investigation />
    </>}
  </main>
}
async function openCurrencyFilters() {
  if (!screen.getByLabelText("Currency").closest("details")?.open)
    await page.getByText(/^Filters/).click()
}

for (const width of [1280, 390]) it(`shows saved zero-payment currencies, preserves actual sums and returns from account history at ${width}px`, async () => {
  await page.viewport(width, 1000)
  render(<QueryClientProvider client={client}><MemoryRouter><Workspace /></MemoryRouter></QueryClientProvider>)
  await screen.findByRole("heading", { name: "Payments matching your filters · 2 transactions · 5 accounts · 4 banks" })
  expect(urls.filter((url) => url.includes("/ledger-accounts?"))).toHaveLength(2)
  const summary = screen.getByRole("region", { name: "Payments matching your filters" })
  expect(within(summary).getByRole("region", { name: "USD · Bank accounts" })).toHaveTextContent("75.00 USD")
  expect(within(summary).getByRole("region", { name: "GBP · Bank accounts" })).toHaveTextContent("No saved statement period is recorded")
  expect(screen.getByLabelText("Accounts with currency not recorded")).toHaveTextContent("1 known account")
  await openCurrencyFilters()
  await page.getByRole("combobox", { name: "Currency", exact: true }).selectOptions("EUR")
  await screen.findByRole("heading", { name: "Payments matching your filters · 0 transactions · 2 accounts · 2 banks" })
  expect(screen.queryByLabelText("Accounts with currency not recorded")).not.toBeInTheDocument()
  expect(screen.getByRole("button", { name: "Download CSV (0)" })).toBeDisabled()
  expect(within(summary).getByRole("region", { name: "EUR · Credit cards" })).toHaveTextContent("0 transactions · 1 account")
  const eur = within(summary).getByRole("region", { name: "EUR · Bank accounts" })
  expect(within(eur).getAllByText("0.00 EUR")).toHaveLength(3)
  await page.screenshot({ path: `/private/tmp/loupe-zero-payment-accounts-${width}.png`, element: summary })
  await page.getByRole("button", { name: "Open Findings" }).click()
  await page.getByRole("button", { name: "Return to Transactions" }).click()
  await screen.findByRole("heading", { name: "Payments matching your filters · 0 transactions · 2 accounts · 2 banks" })
  expect(screen.getByLabelText("Currency")).toHaveValue("EUR")
  await page.getByText("View all 2 accounts and 2 banks", { exact: true }).click()
  const historyName = "View account history for Example Bank · 0002 · Example Company"
  await page.getByRole("button", { name: historyName, exact: true }).click()
  const dialog = await screen.findByRole("dialog")
  await within(dialog).findByText("No activity confirmed")
  expect(dialog).toHaveTextContent("50.00 EUR")
  expect(urls.find((url) => url.includes("/account-history?"))).toContain("account_id=eur")
  await page.getByRole("button", { name: "Close", exact: true }).click()
  expect(screen.getByRole("button", { name: historyName })).toHaveFocus()
  expect(screen.getByLabelText("Currency")).toHaveValue("EUR")
  if (width === 390) return
  await page.getByText(/^Date range/).click()
  await page.getByLabelText("Transactions from", { exact: true }).fill("2026-01-01")
  await page.getByLabelText("Transactions to", { exact: true }).fill("2026-01-31")
  await page.getByRole("button", { name: "Apply", exact: true }).click()
  await screen.findByRole("heading", { name: "Payments matching your filters · 0 transactions · 1 accounts · 1 banks" })
  expect(screen.queryByRole("region", { name: "EUR · Credit cards" })).not.toBeInTheDocument()
  expect(screen.queryByText(/known accounts have no usable saved statement dates/)).not.toBeInTheDocument()
  await page.getByRole("button", { name: "Reset", exact: true }).click()
  await openCurrencyFilters()
  await page.getByRole("combobox", { name: "Currency", exact: true }).selectOptions("GBP")
  await page.getByLabelText("Transactions from", { exact: true }).fill("2026-01-01")
  await page.getByLabelText("Transactions to", { exact: true }).fill("2026-01-31")
  await page.getByRole("button", { name: "Apply", exact: true }).click()
  await screen.findByText(/1 known accounts have no usable saved statement dates/)
  await openCurrencyFilters()
  await page.getByRole("combobox", { name: "Currency", exact: true }).selectOptions("EUR")
  expect(screen.queryByText(/known accounts have no usable saved statement dates/)).not.toBeInTheDocument()
  await page.getByText("All banks", { exact: true }).click()
  await page.getByRole("checkbox", { name: "Example Bank", exact: true }).click()
  await page.getByText("All accounts, across banks", { exact: true }).click()
  await page.getByRole("checkbox", { name: "Example Bank · 0002 · Example Company · EUR", exact: true }).click()
  await page.getByText("All account holders", { exact: true }).click()
  await page.getByRole("checkbox", { name: "Example Company", exact: true }).click()
  await waitFor(() => expect(screen.getByRole("heading", { name: "Payments matching your filters · 0 transactions · 1 accounts · 1 banks" })).toBeVisible())
  expect(screen.getByLabelText("Currency")).toHaveValue("EUR")
  expect(urls.filter((url) => url.includes("/ledger?")).at(-1)).toContain("account_ids=eur")
  expect(screen.getByRole("region", { name: "EUR · Bank accounts" })).toHaveTextContent("0 transactions · 1 account")
}, 30000)
