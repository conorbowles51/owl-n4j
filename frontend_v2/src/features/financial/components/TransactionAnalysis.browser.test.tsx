import "@/styles/globals.css"
import "../financial-workspace.css"
import { useState } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  render,
  screen,
  fireEvent,
  within,
  cleanup,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { LedgerRowBrowser } from "./LedgerRowBrowser"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import type { LedgerTransaction } from "../api"
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
vi.mock("../hooks/use-financial-finding-index", () => ({
  useFinancialFindingIndex: () => ({ data: [], isError: false }),
}))
vi.mock("./LedgerExportButton", () => ({
  LedgerExportButton: ({ tableView }: { tableView: unknown }) => (
    <output data-testid="captured-export">{JSON.stringify(tableView)}</output>
  ),
}))
const rows: LedgerTransaction[] = [
  {
    ...paymentFixture,
    key: "in",
    ref_id: "TX-IN",
    description: "Customer receipt",
    account_holder: "Trading Co",
    account_label: "Trading Co · Bank A",
    account_type: "checking",
    currency: "USD",
    from_name: "Customer",
    to_name: "Trading Co",
    amount_minor: "250000",
    category: "Income",
  },
  {
    ...paymentFixture,
    key: "out",
    ref_id: "TX-OUT",
    description: "Rent payment",
    direction: "debit",
    account_holder: "Trading Co",
    account_label: "Trading Co · Bank A",
    account_type: "checking",
    currency: "USD",
    from_name: "Trading Co",
    to_name: "Landlord",
    amount_minor: "100000",
    category: "Rent",
  },
  {
    ...paymentFixture,
    key: "internal",
    ref_id: "TX-INT",
    description: "Transfer to sister company",
    direction: "debit",
    account_holder: "Trading Co",
    account_label: "Trading Co · Bank A",
    account_type: "checking",
    currency: "USD",
    from_name: "Trading Co",
    to_name: "Sister Co",
    amount_minor: "50000",
    category: "Transfers",
  },
  {
    ...paymentFixture,
    key: "card",
    description: "Card purchase",
    account_label: "Trading Co · Card",
    account_type: "credit_card",
    currency: "USD",
    from_name: "Trading Co",
    to_name: "Shop",
    direction: "debit",
    amount_minor: "2000",
    category: "Shopping",
  },
  {
    ...paymentFixture,
    key: "eur",
    description: "Euro fee",
    account_label: "Trading Co · EUR",
    account_type: "checking",
    from_name: "Trading Co",
    to_name: "Bank",
    direction: "debit",
    amount_minor: "3480",
    category: "Fees",
  },
]
function Workspace() {
  const [source, setSource] = useState<LedgerTransaction | null>(null)
  return (
    <main className="financial-workspace min-h-screen bg-background p-4 text-foreground">
      <h1 className="mb-3 text-lg">Transactions · Acceptance case</h1>
      <LedgerRowBrowser
        investigation
        transactions={rows}
        exportContext={{ caseId: "analysis", params: {} }}
        onSource={setSource}
      />
      {source && (
        <div role="dialog" aria-label="Original statement">
          <p>{source.description}</p>
          <button onClick={() => setSource(null)}>Close original</button>
        </div>
      )}
    </main>
  )
}
afterEach(() => {
  cleanup()
  useFinancialDraftStore.setState({ drafts: {} })
  document.documentElement.classList.remove("dark")
})
it("keeps reciprocal filters, perspective, charts, source and export connected on the same page", async () => {
  await page.viewport(1440, 1100)
  render(
    <QueryClientProvider client={new QueryClient()}>
      <Workspace />
    </QueryClientProvider>
  )
  expect(
    screen.getByText("USD · Credit cards", { selector: "h4" })
  ).toBeVisible()
  expect(
    screen.getByText("USD · Bank accounts", { selector: "h4" })
  ).toBeVisible()
  expect(
    screen.getByText("EUR · Bank accounts", { selector: "h4" })
  ).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "▸ From & To" }))
  const senders = screen.getByRole("region", { name: "Senders (From)" })
  fireEvent.click(within(senders).getByRole("button", { name: "Trading Co" }))
  expect(screen.getByText("4 of 5 imported transactions")).toBeVisible()
  fireEvent.click(
    within(screen.getByRole("region", { name: "Recipients (To)" })).getByRole(
      "button",
      { name: "Landlord" }
    )
  )
  expect(screen.getByText("1 of 5 imported transactions")).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Rent payment" }))
  expect(
    screen.getByRole("dialog", { name: "Original statement" })
  ).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Close original" }))
  expect(
    JSON.parse(screen.getByTestId("captured-export").textContent!)
  ).toMatchObject({
    from_names: ["name:Trading Co"],
    to_names: ["name:Landlord"],
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Clear analysis filters" })
  )
  fireEvent.click(screen.getByRole("button", { name: "▸ Money flow" }))
  const perspective = screen.getByRole("region", { name: "Perspective names" })
  fireEvent.click(
    within(perspective).getByRole("button", { name: "Trading Co" })
  )
  fireEvent.click(
    within(perspective).getByRole("button", { name: "Sister Co" })
  )
  const flow = screen.getByRole("region", {
    name: "Money flow USD · Bank accounts",
  })
  expect(within(flow).getByText("500.00 USD")).toBeVisible()
  fireEvent.click(
    within(flow).getByRole("button", { name: /Internal entries/ })
  )
  expect(screen.getByText("1 of 5 imported transactions")).toBeVisible()
  expect(
    JSON.parse(screen.getByTestId("captured-export").textContent!)
  ).toMatchObject({
    flow_kind: "internal",
    perspective_names: ["name:Trading Co", "name:Sister Co"],
    analysis_group: "USD:bank",
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Clear analysis filters" })
  )
  fireEvent.click(screen.getByRole("button", { name: "▸ Charts" }))
  fireEvent.change(screen.getByLabelText("Chart currency and account type"), {
    target: { value: "USD:bank" },
  })
  fireEvent.click(
    within(
      screen.getByRole("region", { name: "Category distribution" })
    ).getByRole("button", { name: /^Category: Rent / })
  )
  expect(screen.getByText("1 of 5 imported transactions")).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: /Show details for Rent payment/ })
  )
  expect(screen.getByText("TX-OUT")).toBeVisible()
  expect(screen.getByText("Printed balance")).toBeVisible()
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(1440)
  fireEvent.click(
    screen.getByRole("button", { name: "Clear analysis filters" })
  )
  screen
    .getByRole("region", { name: "Transaction analysis" })
    .scrollIntoView({ block: "start" })
  fireEvent.click(
    within(screen.getByRole("region", { name: "Perspective names" })).getByRole(
      "button",
      { name: "Trading Co" }
    )
  )
  fireEvent.click(
    within(screen.getByRole("region", { name: "Perspective names" })).getByRole(
      "button",
      { name: "Sister Co" }
    )
  )
  await page.screenshot({
    path: "../../../../../output/financial-transactions-analysis-light.png",
    element: screen.getByRole("region", {
      name: "Money flow USD · Bank accounts",
    }),
  })
  document.documentElement.classList.add("dark")
  await page.viewport(1155, 900)
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(1155)
  screen
    .getByRole("table", { name: "Investigation transactions" })
    .scrollIntoView({ block: "center" })
  await page.screenshot({
    path: "../../../../../output/financial-transactions-analysis-dark.png",
    element: screen.getByRole("table", { name: "Investigation transactions" }),
  })
}, 30000)

it("filters every dashboard panel through bar segments and doughnut slices, and exposes all 27 categories", async () => {
  await page.viewport(1440, 1100)
  const many = Array.from(
    { length: 27 },
    (_, i): LedgerTransaction => ({
      ...rows[1],
      key: `category-${i + 1}`,
      ref_id: `TX-CAT-${i + 1}`,
      description: `Purchase ${i + 1}`,
      category: `Category ${String(i + 1).padStart(2, "0")}`,
      to_name: `Merchant ${i + 1}`,
      ordering_date: i === 26 ? "2024-02-03" : "2024-01-03",
      amount_minor: "100",
    })
  )
  many.push({
    ...many[0],
    key: "credit",
    direction: "credit",
    from_name: "Merchant 1",
    to_name: "Trading Co",
    amount_minor: "500",
  })
  many.push({
    ...many[0],
    key: "later",
    ordering_date: "2024-02-10",
    amount_minor: "700",
  })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <main className="financial-workspace p-4 bg-background text-foreground">
        <LedgerRowBrowser
          investigation
          transactions={many}
          exportContext={{ caseId: "segments", params: {} }}
        />
      </main>
    </QueryClientProvider>
  )
  fireEvent.click(screen.getByRole("button", { name: "▸ Charts" }))
  expect(screen.getByText("1–8 of 27 categories")).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Next categories" }))
  expect(screen.getByText("9–16 of 27 categories")).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Next categories" }))
  fireEvent.click(screen.getByRole("button", { name: "Next categories" }))
  expect(screen.getByText("25–27 of 27 categories")).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: /^Category: Category 27 / })
  )
  expect(screen.getByText("1 of 29 imported transactions")).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Clear analysis filters" })
  )
  fireEvent.change(screen.getByLabelText("Search chart categories"), {
    target: { value: "Category 27" },
  })
  expect(screen.getByText("1–1 of 1 matching (27 total)")).toBeVisible()
  fireEvent.change(screen.getByLabelText("Search chart categories"), {
    target: { value: "" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: /^Filter category Category 01:/ })
  )
  expect(screen.getByText("3 of 29 imported transactions")).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "2024-01: Money out 1.00 USD" })
  )
  expect(screen.getByText("1 of 29 imported transactions")).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "▸ From & To" }))
  expect(
    within(screen.getByRole("region", { name: "Recipients (To)" })).getByRole(
      "button",
      { name: "Merchant 1" }
    )
  ).toBeVisible()
  expect(
    within(screen.getByRole("region", { name: "Recipients (To)" })).queryByRole(
      "button",
      { name: "Merchant 2" }
    )
  ).toBeNull()
  expect(
    JSON.parse(screen.getByTestId("captured-export").textContent!)
  ).toMatchObject({
    analysis_period: "2024-01",
    analysis_direction: "debit",
    analysis_categories: ["Category 01"],
  })
  fireEvent.click(
    screen.getByRole("button", { name: "2024-01: Money out 1.00 USD" })
  )
  expect(screen.getByText("3 of 29 imported transactions")).toBeVisible()
  fireEvent.keyDown(
    screen.getByRole("button", { name: /^Filter category Category 27:/ }),
    { key: "Enter" }
  )
  expect(screen.getByText("4 of 29 imported transactions")).toBeVisible()
  await page.screenshot({
    path: "../../../../../output/financial-chart-filters.png",
    element: screen.getByRole("region", { name: "Transaction analysis" }),
  })
})
