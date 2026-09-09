import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { StatementRunningBalances } from "./StatementRunningBalances"
vi.mock("./LedgerSourceDialog", () => ({
  LedgerSourceDialog: ({ transactionId }: { transactionId: string }) => (
    <p>Source {transactionId}</p>
  ),
}))
afterEach(() => vi.restoreAllMocks())
const walk = {
  compared_intervals: 2,
  mismatch_count: 1,
  unanchored_balances: 0,
  excluded_rows: 1,
  trailing_rows_without_balance: 0,
  findings_truncated: false,
  findings: [
    {
      before_ref: null,
      after_ref: "TX-1",
      after_transaction_id: "transaction",
      expected_minor: "51000",
      printed_minor: "50000",
      delta_minor: "-1000",
    },
  ],
}
const comparison = {
  available: true,
  reason: null,
  currency: "GBP",
  limitation: "Both orders are conditional; no proof class changes.",
  interpretations: [
    { order: "source_row_order", current: walk },
    { order: "reverse_source_row_order", current: walk },
  ],
}
const answer = {
  case_id: "case",
  period_id: "period",
  source_document_id: "document",
  source_status: "admitted",
  proof_class: "p3",
  applied: false,
  checked_at: "2026-09-09T13:00:00Z",
  comparison,
}
function mount(data: unknown = answer) {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async () => new Response(JSON.stringify(data)))
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <StatementRunningBalances
        caseId="case"
        periodId="period"
        sourceDocumentId="document"
        currency="GBP"
      />
    </QueryClientProvider>
  )
  return { client, fetch }
}
const open = () =>
  fireEvent.click(
    screen.getByRole("button", { name: "Check running balances" })
  )
it("shows both current interpretations and opens a discrepant row source without a correction", async () => {
  const { fetch } = mount()
  expect(fetch).not.toHaveBeenCalled()
  open()
  expect(await screen.findByText("Assuming source row order")).toBeVisible()
  expect(screen.getByText("Assuming reverse source row order")).toBeVisible()
  expect(screen.queryByText(/Proposed correction/)).not.toBeInTheDocument()
  expect(screen.getAllByText(/difference -10.00 GBP/)).toHaveLength(2)
  fireEvent.click(
    screen.getAllByRole("button", { name: "View source: TX-1" })[0]
  )
  expect(screen.getByText("Source transaction")).toBeVisible()
})
it.each([
  { case_id: "other" },
  { period_id: "other" },
  { source_document_id: "other" },
  { applied: true },
  { comparison: { ...comparison, currency: "USD" } },
])("rejects stale scope %j", async (changes) => {
  mount({ ...answer, ...changes })
  open()
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Running balances unavailable"
  )
})
it("keeps absent running balances explicit", async () => {
  mount({
    ...answer,
    comparison: {
      available: false,
      reason: "No stored running balances.",
      interpretations: [],
    },
  })
  open()
  expect(await screen.findByText("No stored running balances.")).toBeVisible()
  expect(screen.queryByText(/0 mismatches/)).not.toBeInTheDocument()
})
it("refreshes with the case ledger after a correction", async () => {
  const { fetch, client } = mount()
  open()
  await screen.findByText("Assuming source row order")
  await client.invalidateQueries({ queryKey: ["financial-ledger", "case"] })
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
})
