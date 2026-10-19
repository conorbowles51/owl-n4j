import "@/styles/globals.css"
import "../financial-workspace.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  act,
  render,
  screen,
  fireEvent,
  cleanup,
  within,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { LedgerRowBrowser } from "./LedgerRowBrowser"
import { WorkspaceScope } from "./InvestigationWorkspaceParts"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import {
  useInvestigationScope,
  useInvestigationScopeStore,
} from "../stores/investigation-scope"
import { showAllImportedPayments } from "../lib/payment-table-draft"
import { useState } from "react"
import { MemoryRouter, Routes, Route } from "react-router-dom"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { RetainedFinancialTab } from "./FinancialNavigation"
import { Button } from "@/components/ui/button"
import type { LedgerTransaction } from "../api"
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(async () => ({
    has_more: false,
    items: [
      ["account-a", "Example Company", "Bank A"],
      ["account-b", "Example Company", "Bank B"],
      ["account-c", "Other Company", "Bank C"],
    ].map(([id, holder, institution]) => ({
      id,
      holder,
      institution,
      identifier: id,
      currency: "USD",
      display_label: `${holder} · ${institution}`,
    })),
    case_id: "case",
    total: 0,
    entries: [],
    categories: ["Due diligence", "Travel"],
  })),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
const rows = Array.from({ length: 123 }, (_, i) => ({
  ...paymentFixture,
  key: `payment-${i}`,
  row_index: i,
  ref_id: `PAY-${i}`,
  description: `Invoice payment ${i + 1}`,
  amount_minor: "10000",
  currency: i < 60 ? "USD" : "EUR",
  account_id: i < 60 ? "account-a" : i < 120 ? "account-b" : "account-c",
  account_holder: i < 120 ? "Example Company" : "Other Company",
  account_label:
    i < 60
      ? "Example Company · Bank A · 001"
      : i < 120
        ? "Example Company · Bank B · 002"
        : "Other Company · Bank A · 003",
}))
function Workspace({
  transactions = rows,
}: {
  transactions?: LedgerTransaction[]
}) {
  const [tab, setTab] = useState("transactions")
  const [params] = useInvestigationScope("case")
  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList>
        <TabsTrigger value="transactions">Transactions</TabsTrigger>
        <TabsTrigger value="findings">Findings & Observations</TabsTrigger>
      </TabsList>
      <RetainedFinancialTab
        value="transactions"
        active={tab === "transactions"}
      >
        <main className="h-screen overflow-auto bg-background p-6 text-foreground space-y-4">
          <header className="flex items-start justify-between">
            <div>
              <h1 className="text-2xl font-semibold">Transactions</h1>
              <p>Synthetic acceptance case · all imported accounts</p>
            </div>
            <Button
              variant="outline"
              onClick={() => showAllImportedPayments("case")}
            >
              Show all imported payments
            </Button>
          </header>
          <WorkspaceScope caseId="case" datesOnly />
          <LedgerRowBrowser
            investigation
            exportContext={{ caseId: "case", params }}
            transactions={transactions}
          />
        </main>
      </RetainedFinancialTab>
      <RetainedFinancialTab value="findings" active={tab === "findings"}>
        <h2>Findings & Observations</h2>
        <input aria-label="Search saved work" />
      </RetainedFinancialTab>
    </Tabs>
  )
}
afterEach(() => {
  cleanup()
  useFinancialDraftStore.setState({ drafts: {} })
  useInvestigationScopeStore.getState().reset()
  vi.restoreAllMocks()
})

it("downloads the complete filtered CSV across pages and reflects a later currency change in its actual contents", async () => {
  await page.viewport(1440, 1000)
  const transactions: LedgerTransaction[] = rows.map((row, index) => ({
    ...row,
    account_institution:
      index < 60 ? "Bank A" : index < 120 ? "Bank B" : "Bank C",
    ordering_date: `2026-${index < 60 ? "01" : "02"}-${String((index % 28) + 1).padStart(2, "0")}`,
    ordering_date_context:
      index === 119 ? "statement_end_ordering_only" : undefined,
    direction: index % 2 ? "credit" : "debit",
    from_name: index % 2 ? 'Client "East", Ltd' : "Example Company",
    to_name: index % 2 ? "Example Company" : 'Supplier "North", LLC',
    category: index % 3 ? "Due diligence" : "Travel",
    label_sources: {
      from_name: { source: "investigator" },
      to_name: { source: "investigator" },
      category: { source: "investigator" },
    },
  }))
  // Observe the browser's real Blob and anchor download without replacing the
  // production CSV serializer or preventing the native download.
  const generated: { blob: Blob; url: string }[] = []
  const downloads: { href: string; filename: string }[] = []
  const createUrl = URL.createObjectURL.bind(URL)
  vi.spyOn(URL, "createObjectURL").mockImplementation((source) => {
    const url = createUrl(source)
    if (source instanceof Blob && source.type.startsWith("text/csv"))
      generated.push({ blob: source, url })
    return url
  })
  const clickAnchor = HTMLAnchorElement.prototype.click
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement
  ) {
    if (this.download)
      downloads.push({ href: this.href, filename: this.download })
    clickAnchor.call(this)
  })
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <Workspace transactions={transactions} />
      </MemoryRouter>
    </QueryClientProvider>
  )
  fireEvent.click(
    screen.getByLabelText("Person or company filter").querySelector("summary")!
  )
  await act(async () => {
    await page
      .getByRole("checkbox", { name: "Example Company", exact: true })
      .click()
  })
  expect(screen.getByText("1–50 of 120 matching rows")).toBeVisible()
  await act(async () => {
    await page
      .getByRole("combobox", { name: "Filter financial payments by category" })
      .selectOptions("Due diligence")
  })
  expect(screen.getByText("1–50 of 80 matching rows")).toBeVisible()
  await act(async () => {
    await page.getByRole("button", { name: "Next ledger rows" }).click()
  })
  expect(screen.getByText("51–80 of 80 matching rows")).toBeVisible()
  expect(
    screen
      .getByRole("table", { name: "Investigation transactions" })
      .querySelectorAll("tbody tr")
  ).toHaveLength(30)
  await act(async () => {
    await page
      .getByRole("button", { name: "Download CSV (80)", exact: true })
      .click()
  })

  async function readDownload(index: number) {
    expect(downloads[index]).toEqual({
      href: generated[index].url,
      filename: "loupe-filtered-transactions.csv",
    })
    expect(generated[index].blob.type).toBe("text/csv;charset=utf-8")
    const text = (await generated[index].blob.text()).replace(/^\uFEFF/, "")
    // Independent decoder for this fully quoted CSV, including embedded commas
    // and doubled quotes. Require every byte to belong to a complete cell.
    const cells = [...text.matchAll(/"((?:[^"]|"")*)"(?:,|\r\n|$)/g)]
    expect(cells.map((cell) => cell[0]).join("")).toBe(text)
    const values = cells.map((cell) => cell[1].replace(/""/g, '"'))
    const headers = values.splice(0, 16)
    expect(headers).toEqual([
      "ref_id",
      "date",
      "description",
      "from",
      "to",
      "category",
      "from_basis",
      "to_basis",
      "category_basis",
      "account",
      "direction",
      "amount",
      "currency",
      "printed_balance",
      "printed_balance_status",
      "notes",
    ])
    expect(values.length % headers.length).toBe(0)
    return Array.from(
      { length: values.length / headers.length },
      (_, rowIndex) =>
        Object.fromEntries(
          headers.map((name, column) => [
            name,
            values[rowIndex * headers.length + column],
          ])
        )
    )
  }
  const exported = await readDownload(0)
  const matching = transactions.filter(
    (_, index) => index < 120 && index % 3 !== 0
  )
  expect(exported).toHaveLength(80)
  expect(exported.map((row) => row.ref_id).sort()).toEqual(
    matching.map((row) => row.ref_id!).sort()
  )
  expect(new Set(exported.map((row) => row.currency))).toEqual(
    new Set(["USD", "EUR"])
  )
  for (const expected of matching) {
    expect(
      exported.find((row) => row.ref_id === expected.ref_id)
    ).toMatchObject({
      date:
        expected.ordering_date_context === "statement_end_ordering_only"
          ? ""
          : expected.ordering_date,
      description: expected.description,
      from: expected.from_name,
      to: expected.to_name,
      category: "Due diligence",
      from_basis: "investigator",
      to_basis: "investigator",
      category_basis: "investigator",
      account: expected.account_label,
      direction: expected.direction,
      amount: "100.00",
      currency: expected.currency,
      printed_balance: "",
      printed_balance_status: "unavailable",
    })
  }
  expect(
    screen.getByRole("combobox", {
      name: "Filter financial payments by category",
    })
  ).toHaveValue("Due diligence")
  expect(
    screen.getByRole("checkbox", { name: /^Example Company$/ })
  ).toBeChecked()
  expect(screen.getByText("51–80 of 80 matching rows")).toBeVisible()
  fireEvent.click(screen.getByText("Filters (1)", { exact: true }))
  await act(async () => {
    await page
      .getByRole("combobox", { name: "Currency", exact: true })
      .selectOptions("EUR")
  })
  expect(screen.getByText("40 of 123 imported transactions")).toBeVisible()
  expect(
    screen
      .getByRole("table", { name: "Investigation transactions" })
      .querySelectorAll("tbody tr")
  ).toHaveLength(40)
  await act(async () => {
    await page
      .getByRole("button", { name: "Download CSV (40)", exact: true })
      .click()
  })
  const narrowed = await readDownload(1)
  expect(narrowed).toHaveLength(40)
  expect(narrowed.map((row) => row.ref_id).sort()).toEqual(
    matching
      .filter((row) => row.currency === "EUR")
      .map((row) => row.ref_id!)
      .sort()
  )
  expect(narrowed.every((row) => row.currency === "EUR")).toBe(true)
  expect(downloads).toHaveLength(2)
  expect(generated).toHaveLength(2)
})
it("starts with all imported payments and filters across banks without a load step", async () => {
  await page.viewport(1440, 1000)
  document.documentElement.classList.remove("dark")
  await act(async () => {
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <MemoryRouter initialEntries={["/cases/case/financial"]}>
          <Routes>
            <Route path="/cases/:id/financial" element={<Workspace />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )
  })
  expect(screen.getByText("1–50 of 123 matching rows")).toBeInTheDocument()
  fireEvent.click(
    screen.getByLabelText("Person or company filter").querySelector("summary")!
  )
  fireEvent.click(
    await screen.findByRole("checkbox", { name: "Example Company" })
  )
  expect(screen.getByText("1–50 of 120 matching rows")).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Next ledger rows" }))
  fireEvent.click(
    screen.getByLabelText("Bank account filter").querySelector("summary")!
  )
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "Bank B · account-b · Example Company · USD",
    })
  )
  expect(screen.getByText("1–50 of 60 matching rows")).toBeVisible()
  fireEvent.click(screen.getByRole("checkbox", { name: "Other Company" }))
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "Bank C · account-c · Other Company · USD",
    })
  )
  expect(screen.getByText("1–50 of 63 matching rows")).toBeVisible()
  fireEvent.change(screen.getByLabelText("Search payments"), {
    target: { value: "Invoice payment 12" },
  })
  fireEvent.mouseDown(
    screen.getByRole("tab", { name: "Findings & Observations" })
  )
  fireEvent.mouseDown(screen.getByRole("tab", { name: "Transactions" }))
  expect(screen.getByLabelText("Search payments")).toHaveValue(
    "Invoice payment 12"
  )
  expect(screen.getByRole("checkbox", { name: "Other Company" })).toBeChecked()
  fireEvent.click(screen.getByRole("button", { name: "Reset view" }))
  expect(screen.getByLabelText("Search payments")).toHaveValue("")
  expect(screen.getByText("1–50 of 123 matching rows")).toBeVisible()
  fireEvent.change(screen.getByLabelText("Search mode"), {
    target: { value: "boolean" },
  })
  fireEvent.change(screen.getByLabelText("Search payments"), {
    target: { value: 'currency:USD OR description:"payment 123"' },
  })
  expect(screen.getByText("1–50 of 61 matching rows")).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: /^Amount/ }))
  const toolbar = screen.getByRole("region", {
    name: "Transaction tools and filters",
  })
  expect(within(toolbar).getByRole("button", { name: /Charts/ })).toBeVisible()
  expect(within(toolbar).getByLabelText("Category")).toBeVisible()
  await page.screenshot({ path: "/tmp/loupe-transaction-workflow.png" })
})
