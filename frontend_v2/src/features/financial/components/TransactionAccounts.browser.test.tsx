import "@/styles/globals.css"
import "../financial-workspace.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, render, screen, fireEvent, cleanup } from "@testing-library/react"
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
import { Button } from "@/components/ui/button"
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(async () => ({
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
  const [params] = useInvestigationScope("case")
  return (
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
        <Workspace />
      </QueryClientProvider>
    )
  })
  expect(screen.getByText("1–50 of 123 matching rows")).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText("Filter account holder"), {
    target: { value: "example company" },
  })
  expect(screen.getByText("1–50 of 120 matching rows")).toBeInTheDocument()
  expect(screen.getAllByText("6,000.00 USD").length).toBeGreaterThan(0)
  expect(screen.getAllByText("6,000.00 EUR").length).toBeGreaterThan(0)
  fireEvent.click(screen.getByRole("button", { name: "Next ledger rows" }))
  expect(screen.getByText("51–100 of 120 matching rows")).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText("Filter imported account"), {
    target: { value: "account-b" },
  })
  expect(screen.getByText("1–50 of 60 matching rows")).toBeInTheDocument()
  fireEvent.click(
    screen.getByText("Date range", { exact: false, selector: "summary" })
  )
  fireEvent.change(screen.getByLabelText("Transactions from"), {
    target: { value: "2026-01-01" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Apply" }))
  expect(screen.getByLabelText("Filter account holder")).toHaveValue(
    "example company"
  )
  expect(screen.getByLabelText("Filter imported account")).toHaveValue(
    "account-b"
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Show all imported payments" })
  )
  expect(screen.getByLabelText("Filter account holder")).toHaveValue("")
  expect(screen.getByLabelText("Filter imported account")).toHaveValue("")
  expect(screen.getByText("1–50 of 123 matching rows")).toBeInTheDocument()
  await page.screenshot({
    path: "../../../../../data/local-runtime/transactions-all-accounts.png",
  })
})
