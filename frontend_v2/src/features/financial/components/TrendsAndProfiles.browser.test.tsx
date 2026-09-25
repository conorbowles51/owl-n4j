import "@/styles/globals.css"
import "../financial-workspace.css"
import {
  render,
  screen,
  fireEvent,
  within,
  cleanup,
  waitFor,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { TrendComparisonWorkspace } from "./TrendComparisonWorkspace"
import { InvestigatorPeople } from "./InvestigatorPeople"
import { trendRows, trendCoverage } from "../lib/trend-fixture.test-support"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import type { AccountParties } from "../lib/account-parties"
let profileRows = trendRows
let profileAccounts: AccountParties["accounts"] = []
const profileCase = "10000000-0000-4000-8000-000000000001"
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(async (url: string) =>
    url.startsWith("/api/financial/account-parties?")
      ? {
          case_id: "10000000-0000-4000-8000-000000000001",
          revision: "a".repeat(64),
          accounts: profileAccounts,
          parties: [],
          history: [],
          applied: false,
          limitation: "Synthetic directory",
        }
      : url.startsWith("/api/financial/account-history?")
        ? {
            case_id: "10000000-0000-4000-8000-000000000001",
            applied: false,
            groups: profileAccounts.slice(-1).map((account) => ({
              key: account.id,
              account_id: account.id,
              currency: account.currency,
              balance_kind: "asset",
              label: `${account.institution} ${account.identifier_as_printed}`,
              periods: [
                {
                  id: "quiet",
                  source_document_id: "source",
                  evidence_file_id: null,
                  filename: "Synthetic quiet statement",
                  start: "2026-01-01",
                  end: "2026-01-31",
                  opening_minor: "5000",
                  closing_minor: "5000",
                  status: "confirmed_no_activity",
                  transaction_count: 0,
                  undated_count: 0,
                  activity: [],
                },
              ],
            })),
          }
        : {
            case_id: "10000000-0000-4000-8000-000000000001",
            has_more: false,
            items: [],
            categories: [],
            entries: [],
          }
  ),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
vi.mock("../hooks/use-financial-finding-index", () => ({
  useFinancialFindingIndex: () => ({ data: [], isError: false }),
}))
vi.mock("../hooks/use-investigator-payments", () => ({
  useInvestigatorPayments: () => ({
    rows: profileRows,
    params: {},
    complete: true,
    query: {
      data: { transactions: profileRows, total: profileRows.length },
      isPending: false,
      isError: false,
    },
  }),
}))
vi.mock("./InvestigationWorkspaceParts", async (original) => ({
  ...(await original<typeof import("./InvestigationWorkspaceParts")>()),
  WorkspaceHeading: ({ title }: { title: string }) => <h1>{title}</h1>,
  WorkspaceScope: () => null,
  InvestigationReadState: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}))
vi.mock("./PaymentComparison", () => ({
  PaymentComparison: ({
    ids,
    title,
    onClose,
  }: {
    ids: string[]
    title: string
    onClose: () => void
  }) => (
    <div role="dialog" aria-label={title}>
      <output>{ids.join(",")}</output>
      <button onClick={onClose}>Close comparison</button>
    </div>
  ),
}))
vi.mock("./LedgerSourceDialog", () => ({
  LedgerSourceDialog: ({
    transactionId,
    onClose,
  }: {
    transactionId: string
    onClose: () => void
  }) => (
    <div role="dialog" aria-label="Original statement">
      <output>{transactionId}</output>
      <button onClick={onClose}>Close original</button>
    </div>
  ),
}))
vi.mock("./LedgerExportButton", () => ({
  LedgerExportButton: ({ tableView }: { tableView: unknown }) =>
    tableView ? (
      <output data-testid="profile-export">{JSON.stringify(tableView)}</output>
    ) : null,
}))
afterEach(() => {
  cleanup()
  profileRows = trendRows
  profileAccounts = []
  useFinancialDraftStore.setState({ drafts: {} })
  document.documentElement.classList.remove("dark")
})
const wrap = (child: React.ReactNode) => (
  <MemoryRouter>
    <QueryClientProvider client={new QueryClient()}>
      <main className="financial-workspace min-h-screen bg-background text-foreground p-4">
        {child}
      </main>
    </QueryClientProvider>
  </MemoryRouter>
)
it("shows evidence-driven trends, preserves a comparison after source navigation and fits narrow layouts", async () => {
  await page.viewport(1440, 1050)
  render(
    wrap(
      <TrendComparisonWorkspace
        caseId="case"
        rows={trendRows}
        coverage={trendCoverage}
        onCoverageRetry={vi.fn()}
      />
    )
  )
  const drivers = screen.getByRole("region", { name: "What drove the change" })
  fireEvent.change(
    within(drivers).getByRole("combobox", { name: "Explain by" }),
    { target: { value: "category" } }
  )
  expect(
    within(drivers).getByText("Services", { selector: "span" })
  ).toBeVisible()
  const returns = screen.getByRole("region", {
    name: "Transfer returns with matching references",
  })
  fireEvent.click(
    within(returns).getByRole("button", { name: "View 2 supporting payments" })
  )
  expect(screen.getByRole("dialog")).toHaveTextContent("out,return")
  fireEvent.click(screen.getByRole("button", { name: "Close comparison" }))
  expect(screen.getByLabelText("earlier start")).toHaveValue("2021-01-01")
  await page.screenshot({
    path: "../../../../../output/financial-investigative-trends-light.png",
    element: drivers,
  })
  await page.viewport(1000, 900)
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(1002)
  document.documentElement.classList.add("dark")
  await page.screenshot({
    path: "../../../../../output/financial-investigative-trends-dark.png",
    element: returns,
  })
})
it("gives each profile the transaction charts and filters without leaking another profile's selection or export", async () => {
  await page.viewport(1440, 1000)
  render(wrap(<InvestigatorPeople caseId={profileCase} />))
  fireEvent.click(
    await screen.findByRole("button", {
      name: /Recorded payment name Software Co/,
    })
  )
  expect(screen.getByRole("button", { name: "▾ Charts" })).toBeVisible()
  expect(screen.getByText("3 of 3 imported transactions")).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", {
      name: "2021-02: 1 transactions, credits 0.00 USD, debits 12.99 USD",
    })
  )
  expect(screen.getByText("1 of 3 imported transactions")).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Payment to Software Co (subscription-feb)",
    })
  )
  expect(
    screen.getByRole("dialog", { name: "Original statement" })
  ).toHaveTextContent("subscription-feb")
  fireEvent.click(screen.getByRole("button", { name: "Close original" }))
  fireEvent.click(screen.getByText("Download these transactions"))
  expect(
    JSON.parse(screen.getByTestId("profile-export").textContent!)
  ).toMatchObject({
    profile_id: "name:Software Co",
    analysis_period: "2021-02",
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Back to names and accounts" })
  )
  fireEvent.click(
    screen.getByRole("button", { name: /Recorded payment name New supplier/ })
  )
  expect(screen.getByText("1 of 1 imported transactions")).toBeVisible()
  expect(
    screen.queryByRole("button", { name: "2021-02 ×" })
  ).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "▸ From & To" }))
  expect(screen.getByRole("region", { name: "Recipients (To)" })).toBeVisible()
  await page.screenshot({
    path: "../../../../../output/financial-profile-analysis.png",
    element: screen.getByRole("region", { name: "Transaction analysis" }),
  })
})

it("shows quiet statement records and keeps a person's five accounts together through filtering, drilldown and return", async () => {
  await page.viewport(1280, 900)
  const holder = {
    id: "20000000-0000-4000-8000-000000000001",
    name: "Example Holder",
  }
  profileAccounts = Array.from({ length: 5 }, (_, n) => ({
    id: `30000000-0000-4000-8000-00000000000${n}`,
    canonical_id: `30000000-0000-4000-8000-00000000000${n}`,
    institution: "Example Bank",
    identifier_as_printed: `000${n}`,
    holder_as_recorded: holder.name,
    currency: n === 4 ? "EUR" : "USD",
    account_type: "checking",
    statement_periods: [
      {
        id: `40000000-0000-4000-8000-00000000000${n}`,
        source_document_id: `50000000-0000-4000-8000-00000000000${n}`,
        start: "2026-01-01",
        end: "2026-01-31",
      },
    ],
    party: null,
    holder_parties: [holder],
    relationships: [],
  }))
  profileRows = [
    {
      ...trendRows[0],
      key: "owned",
      account_id: profileAccounts[0].id,
      account_holder_parties: [holder],
      source_document_id:
        profileAccounts[0].statement_periods![0].source_document_id,
    },
    {
      ...trendRows[1],
      key: "appearance",
      account_id: "outsider",
      counterparty_link: { kind: "party", id: holder.id, label: holder.name },
    },
  ]
  render(wrap(<InvestigatorPeople caseId={profileCase} />))
  await screen.findByRole("button", {
    name: /Reviewed account holder Example Holder/,
  })
  fireEvent.change(screen.getByRole("combobox", { name: "Show" }), {
    target: { value: "account" },
  })
  fireEvent.change(
    screen.getByRole("combobox", { name: "Profile currency and account type" }),
    { target: { value: "EUR:bank" } }
  )
  const quietCard = screen.getByRole("button", {
    name: /Account Example Bank.*0004/,
  })
  expect(quietCard).toHaveTextContent("0 matching payments")
  expect(quietCard).toHaveTextContent("1 account · 1 bank · 1 source document")
  expect(quietCard).toHaveTextContent("Currencies recorded: EUR")
  expect(quietCard).toHaveTextContent(
    "Saved statement dates: 2026-01-01 to 2026-01-31"
  )
  expect(quietCard).toHaveTextContent("Payment dates: No matching payments")
  expect(quietCard).not.toHaveTextContent("0 accounts")
  await page.screenshot({
    path: "/private/tmp/loupe-quiet-profile-list-1280.png",
  })
  fireEvent.click(quietCard)
  const savedSummary = screen.getByRole("group", {
    name: "Saved account and statement records",
  })
  expect(savedSummary).toHaveTextContent("1 source document")
  expect(screen.queryByText("Currencies: None")).not.toBeInTheDocument()
  expect(
    await screen.findByRole("region", { name: "Account balances and activity" })
  ).toBeVisible()
  const quietPanel = savedSummary.closest(".finance-panel") as HTMLElement
  await page.screenshot({
    path: "/private/tmp/loupe-quiet-profile-1280.png",
    element: quietPanel,
  })
  await page.viewport(390, 900)
  await waitFor(() =>
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(392)
  )
  await page.screenshot({
    path: "/private/tmp/loupe-quiet-profile-390.png",
    element: quietPanel,
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Back to names and accounts" })
  )
  expect(screen.getByRole("combobox", { name: "Show" })).toHaveValue("account")
  expect(
    screen.getByRole("combobox", { name: "Profile currency and account type" })
  ).toHaveValue("EUR:bank")
  expect(
    screen.getByRole("button", { name: /Account Example Bank.*0004/ })
  ).toHaveTextContent("1 source document")
  fireEvent.change(
    screen.getByRole("combobox", { name: "Profile currency and account type" }),
    { target: { value: "" } }
  )
  fireEvent.change(screen.getByRole("combobox", { name: "Show" }), {
    target: { value: "all" },
  })
  await page.viewport(1280, 900)
  fireEvent.click(
    await screen.findByRole("button", {
      name: /Reviewed account holder Example Holder/,
    })
  )
  const accountList = screen.getByRole("region", {
    name: "Accounts belonging to this person or business",
  })
  expect(within(accountList).getAllByRole("button")).toHaveLength(5)
  expect(accountList).not.toHaveTextContent("outsider")
  expect(screen.getByText("1 of 1 imported transactions")).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "As sender or beneficiary (1)" })
  )
  fireEvent.click(screen.getByText("Download these transactions"))
  expect(
    JSON.parse(screen.getByTestId("profile-export").textContent!)
  ).toMatchObject({
    profile_id: `owner:${holder.id}`,
    profile_scope: "counterparty_payments",
  })
  await page.screenshot({
    path: "/private/tmp/loupe-person-accounts-wide.png",
    element: accountList,
  })
  fireEvent.click(within(accountList).getByRole("button", { name: /0004/ }))
  expect(
    await screen.findByRole("region", { name: "Account balances and activity" })
  ).toBeVisible()
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "2026-01" })).toBeVisible()
  )
  fireEvent.click(screen.getByRole("button", { name: "2026-01" }))
  expect(
    screen.getByRole("region", { name: "Account balances and activity" })
  ).toHaveTextContent("Confirmed quiet period")
  fireEvent.click(
    screen.getByRole("button", { name: "Back to person or business" })
  )
  expect(
    screen.getByRole("region", {
      name: "Accounts belonging to this person or business",
    })
  ).toBeVisible()
  await page.viewport(420, 900)
  await waitFor(() =>
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(422)
  )
  await page.screenshot({
    path: "/private/tmp/loupe-person-accounts-narrow.png",
    element: screen.getByRole("region", {
      name: "Accounts belonging to this person or business",
    }),
  })
})
