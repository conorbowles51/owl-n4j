import "@/styles/globals.css"
import "../financial-workspace.css"
import {
  render,
  screen,
  fireEvent,
  within,
  cleanup,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { TrendComparisonWorkspace } from "./TrendComparisonWorkspace"
import { InvestigatorPeople } from "./InvestigatorPeople"
import { trendRows, trendCoverage } from "../lib/trend-fixture.test-support"
import { useFinancialDraftStore } from "../stores/financial-drafts"
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
vi.mock("../hooks/use-financial-finding-index", () => ({
  useFinancialFindingIndex: () => ({ data: [], isError: false }),
}))
vi.mock("../hooks/use-investigator-payments", () => ({
  useInvestigatorPayments: () => ({
    rows: trendRows,
    params: {},
    complete: true,
    query: {
      data: { transactions: trendRows, total: trendRows.length },
      isPending: false,
      isError: false,
    },
  }),
}))
vi.mock("./InvestigationWorkspaceParts", () => ({
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
  render(wrap(<InvestigatorPeople caseId="case" />))
  fireEvent.click(
    screen.getByRole("button", { name: /Recorded payment name Software Co/ })
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
