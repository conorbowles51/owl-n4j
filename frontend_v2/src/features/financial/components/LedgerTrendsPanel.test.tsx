import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, fireEvent } from "@testing-library/react"
import { it, expect, vi, afterEach } from "vitest"
import { LedgerTrendsPanel } from "./LedgerTrendsPanel"
vi.mock("./LinkedPayments", () => ({
  LinkedPayments: ({ caseId, ids }: { caseId: string; ids: string[] }) => (
    <p data-testid="linked-payments">
      {caseId}/{ids.join(",")}
    </p>
  ),
}))
afterEach(() => vi.restoreAllMocks())
const totals = {
  currency: "GBP",
  rows: 1,
  credits_minor: "9007199254740993",
  debits_minor: "0",
  net_minor: "9007199254740993",
}
const answer = {
  case_id: "case-a",
  account_id: null,
  start_date: null,
  end_date: null,
  grouping: "monthly",
  date_basis: "ordering_date",
  available: true,
  reason: null,
  applied: false,
  limitation: "Not complete evidence.",
  included_rows: 1,
  excluded_rows: 0,
  currencies: [totals],
  points: [
    {
      ...totals,
      date: "2026-01-01",
      transaction_ids: ["tx-a"],
      source_document_ids: ["doc-a"],
    },
  ],
}
function mount(
  data: unknown = answer,
  population: "working" | "verified" = "verified"
) {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async () => new Response(JSON.stringify(data)))
  const client = new QueryClient()
  const element = (caseId = "case-a") => (
    <QueryClientProvider client={client}>
      <LedgerTrendsPanel caseId={caseId} params={{}} population={population} />
    </QueryClientProvider>
  )
  const view = render(element())
  return { fetch, change: () => view.rerender(element("case-b")) }
}
it("loads exact date totals on request and passes only contributing payments to the payment browser", async () => {
  const { fetch, change } = mount()
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Show totals" }))
  expect(
    await screen.findByText(/Credits: 90,071,992,547,409.93 GBP/)
  ).toBeInTheDocument()
  expect(screen.getByTestId("linked-payments")).toHaveTextContent("case-a/tx-a")
  change()
  expect(screen.queryByTestId("linked-payments")).not.toBeInTheDocument()
  expect(screen.queryByText(/Credits:/)).not.toBeInTheDocument()
})
it.each([
  { case_id: "other" },
  { grouping: "daily" },
  { account_id: "other" },
  { date_basis: "transaction_date" },
  { points: [{ ...answer.points[0], credits_minor: "1" }] },
  { points: [{ ...answer.points[0], transaction_ids: ["tx-a", "tx-a"] }] },
  { currencies: [{ ...totals, credits_minor: "4" }] },
])("refuses mismatched date totals %j", async (change) => {
  mount({ ...answer, ...change })
  fireEvent.click(screen.getByRole("button", { name: "Show totals" }))
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Date totals unavailable"
  )
  expect(screen.queryByText(/Credits:/)).not.toBeInTheDocument()
})
it("keeps unknown separate from empty activity", async () => {
  mount({
    ...answer,
    available: false,
    reason: "Too many rows.",
    included_rows: null,
    excluded_rows: null,
    currencies: [],
    points: [],
  })
  fireEvent.click(screen.getByRole("button", { name: "Show totals" }))
  expect(
    await screen.findByText("Date totals unavailable. Too many rows.")
  ).toBeInTheDocument()
  expect(screen.queryByText(/No eligible payments/)).not.toBeInTheDocument()
})

it("uses the explicit working population and preserves exact amounts", async () => {
  const { fetch } = mount({ ...answer, population: "working" }, "working")
  fireEvent.click(screen.getByRole("button", { name: "Show totals" }))
  expect(
    await screen.findByText(/Credits: 90,071,992,547,409.93 GBP/)
  ).toBeInTheDocument()
  expect(String(fetch.mock.calls[0][0])).toContain("ledger-working-analysis")
})
it("refuses verified data returned to a working analysis", async () => {
  mount(answer, "working")
  fireEvent.click(screen.getByRole("button", { name: "Show totals" }))
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "different population"
  )
})
