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
    categories: [],
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
function Workspace() {
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
            transactions={rows}
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
    screen.getByRole("checkbox", { name: "Example Company · Bank B · USD" })
  )
  expect(screen.getByText("1–50 of 60 matching rows")).toBeVisible()
  fireEvent.click(screen.getByRole("checkbox", { name: "Other Company" }))
  fireEvent.click(
    screen.getByRole("checkbox", { name: "Other Company · Bank C · USD" })
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
