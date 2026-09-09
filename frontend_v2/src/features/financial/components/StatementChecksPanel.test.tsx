import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { it, expect, vi, afterEach } from "vitest"
import { StatementChecksPanel } from "./StatementChecksPanel"
afterEach(() => vi.restoreAllMocks())
const period = {
  period_id: "period",
  account_id: "account",
  account_label: "Review account",
  source_document_id: "document",
  source_status: "superseded",
  proof_class: "p3",
  currency: "USD",
  start: "2026-01-01",
  end: "2026-01-31",
  opening_source: "printed",
  closing_source: "printed",
  recorded_status: "balanced",
  recorded_at: null,
  status: "unbalanced",
  reason: null,
  amounts: {
    opening: "100",
    credits: "9007199254740993",
    debits: "0",
    computed_closing: "9007199254741093",
    closing: "100",
    difference: "9007199254740993",
  },
  counted_rows: 2,
  excluded_rows: 1,
  independent: true,
}
const answer = {
  case_id: "case",
  offset: 0,
  has_more: false,
  applied: false,
  checked_at: "2026-09-09T13:00:00Z",
  limitation: "No proof of complete extraction.",
  items: [period],
}
function mount(data: unknown = answer) {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async () => new Response(JSON.stringify(data)))
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const view = render(
    <QueryClientProvider client={client}>
      <StatementChecksPanel caseId="case" />
    </QueryClientProvider>
  )
  return { fetch, client, ...view }
}
function open() {
  fireEvent.click(
    screen.getByRole("button", { name: "Check statement balances" })
  )
}
it("checks on request with exact amounts, exclusions and old result clearly distinguished", async () => {
  const { fetch } = mount()
  expect(fetch).not.toHaveBeenCalled()
  open()
  expect(await screen.findByText("Balance difference")).toBeVisible()
  expect(screen.getAllByText(/90071992547409\.93/)).toHaveLength(2)
  expect(screen.getByText(/Source: superseded · P3/)).toBeVisible()
  expect(
    screen.getByText(/2 admitted rows counted; 1 other rows excluded/)
  ).toBeVisible()
  expect(screen.getByText(/Earlier stored check: balanced/)).toBeInTheDocument()
  expect(
    fetch.mock.calls.every(
      ([, options]) => !options?.method || options.method === "GET"
    )
  ).toBe(true)
})
it.each([
  { case_id: "other" },
  { offset: 25 },
  { applied: true },
  { items: [{ ...period, status: "balanced" }] },
  {
    items: [
      { ...period, amounts: { ...period.amounts, credits: Number("9007199254740993") } },
    ],
  },
])("refuses incorrect scope or arithmetic %j", async (change) => {
  mount({ ...answer, ...change })
  open()
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Balance checks unavailable"
  )
  expect(screen.queryByText("Review account · USD")).not.toBeInTheDocument()
})
it("shows absent controls as unknown and never a zero difference", async () => {
  mount({
    ...answer,
    items: [
      {
        ...period,
        status: "unavailable",
        reason: "Opening balance missing",
        independent: false,
        amounts: {
          ...period.amounts,
          opening: null,
          computed_closing: null,
          difference: null,
        },
      },
    ],
  })
  open()
  expect(await screen.findByText("Missing balances")).toBeVisible()
  expect(screen.getAllByText("Unknown")).toHaveLength(3)
})
it("refreshes when a ledger correction invalidates this case", async () => {
  const { client, fetch } = mount()
  open()
  await screen.findByText("Balance difference")
  await client.invalidateQueries({ queryKey: ["financial-ledger", "case"] })
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
})
it("keeps refused periods and missing periods explicit", async () => {
  mount({
    ...answer,
    items: [
      {
        ...period,
        status: "refused",
        amounts: null,
        reason: "Currency mismatch",
        independent: null,
        counted_rows: null,
        excluded_rows: null,
      },
    ],
  })
  open()
  expect(await screen.findByText("Could not check")).toBeVisible()
  expect(screen.getByText("Currency mismatch")).toBeVisible()
  expect(screen.queryByText("Opening balance")).not.toBeInTheDocument()
})
