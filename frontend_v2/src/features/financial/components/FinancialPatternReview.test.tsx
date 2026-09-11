import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, fireEvent, cleanup } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { FinancialPatternReview } from "./FinancialPatternReview"
vi.mock("./InvestigationFilters", () => ({ InvestigationFilters: () => null }))
vi.mock("./PaymentClaimComparison", () => ({
  PaymentClaimComparison: () => null,
}))
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})
it("opts into path screening and clears captured results when criteria change", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(
      async () =>
        new Response(
          JSON.stringify({
            schema: "loupe.financial.pattern_review/1",
            case_id: "case",
            account_id: null,
            start_date: null,
            end_date: null,
            population: "working",
            window_days: 3,
            cross_account: true,
            snapshot_sha256: "a".repeat(64),
            reviewed_rows: 4,
            date_unavailable_ids: [],
            hypotheses: [],
            limitation: "Captured path criteria",
          })
        )
    )
  render(
    <QueryClientProvider client={new QueryClient()}>
      <FinancialPatternReview caseId="case" />
    </QueryClientProvider>
  )
  expect(
    screen.getByLabelText("Screen paths between accounts")
  ).not.toBeChecked()
  fireEvent.click(screen.getByLabelText("Screen paths between accounts"))
  fireEvent.click(
    screen.getByRole("button", { name: "Screen captured ledger" })
  )
  expect(await screen.findByText("Captured path criteria")).toBeInTheDocument()
  expect(String(fetch.mock.calls[0][0])).toContain("cross_account=true")
  fireEvent.click(screen.getByLabelText("Screen paths between accounts"))
  expect(screen.queryByText("Captured path criteria")).not.toBeInTheDocument()
})
