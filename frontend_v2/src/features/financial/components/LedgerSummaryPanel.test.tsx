import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, act } from "@testing-library/react"
import { it, expect, vi, afterEach } from "vitest"
import { LedgerSummaryPanel } from "./LedgerSummaryPanel"
afterEach(() => vi.restoreAllMocks())
const answer = {
  case_id: "case-a",
  account_id: null,
  start_date: null,
  end_date: null,
  included_classes: ["p0", "p1", "p2"],
  max_rows: 10000,
  available: true,
  reason: null,
  considered_rows: 3,
  included_rows: 2,
  excluded_rows: 1,
  applied: false,
  limitation: "Postings are not an account balance.",
  exclusions: {
    quarantined: 0,
    superseded: 1,
    rejected: 0,
    source_not_admitted: 0,
    proof_class_not_included: 0,
  },
  currencies: [
    {
      currency: "GBP",
      rows: 2,
      credits_minor: "9007199254740993",
      debits_minor: "9007199254740995",
      net_minor: "-2",
    },
  ],
}
function mount(initial: unknown = answer) {
  let data = initial
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async () => new Response(JSON.stringify(data)))
  const client = new QueryClient()
  const element = (accountId?: string) => (
    <QueryClientProvider client={client}>
      <LedgerSummaryPanel caseId="case-a" params={{ accountId }} />
    </QueryClientProvider>
  )
  const view = render(element())
  return {
    fetch,
    client,
    set: (next: unknown) => {
      data = next
    },
    account: (id: string) => view.rerender(element(id)),
  }
}
it("renders exact large amounts, signed net and excluded populations", async () => {
  mount()
  expect(
    await screen.findByText("Credits: 90071992547409.93 GBP")
  ).toBeInTheDocument()
  expect(screen.getByText("Debits: 90071992547409.95 GBP")).toBeInTheDocument()
  expect(screen.getByText("Net postings: -0.02 GBP")).toBeInTheDocument()
  expect(
    screen.getByText("2 included rows; 1 excluded from 3 rows in this scope.")
  ).toBeInTheDocument()
  expect(screen.getByText("Superseded readings: 1")).toBeInTheDocument()
})
it.each([
  { case_id: "other" },
  { account_id: "other" },
  { start_date: "2026-01-01" },
  { excluded_rows: 2 },
  { applied: true },
  { currencies: [{ ...answer.currencies[0], net_minor: "10" }] },
])("refuses inconsistent summary %j", async (change) => {
  mount({ ...answer, ...change })
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Summary unavailable"
  )
  expect(screen.queryByText(/Credits:/)).not.toBeInTheDocument()
})
it("keeps unavailable distinct from zero", async () => {
  mount({
    ...answer,
    available: false,
    reason: "Narrow the dates.",
    considered_rows: null,
    included_rows: null,
    excluded_rows: null,
    exclusions: null,
    currencies: [],
  })
  expect(
    await screen.findByText("Summary unavailable. Narrow the dates.")
  ).toBeInTheDocument()
  expect(screen.queryByText(/No eligible postings/)).not.toBeInTheDocument()
})
it("refreshes after the same case ledger invalidation used by corrections", async () => {
  const { client, set, fetch } = mount()
  await screen.findByText("Credits: 90071992547409.93 GBP")
  set({
    ...answer,
    currencies: [
      {
        ...answer.currencies[0],
        credits_minor: "1235",
        debits_minor: "0",
        net_minor: "1235",
      },
    ],
  })
  await act(async () => {
    await client.invalidateQueries({ queryKey: ["financial-ledger", "case-a"] })
  })
  expect(await screen.findByText("Credits: 12.35 GBP")).toBeInTheDocument()
  expect(
    screen.queryByText("Credits: 90071992547409.93 GBP")
  ).not.toBeInTheDocument()
  expect(fetch).toHaveBeenCalledTimes(2)
})
it("does not retain old totals when account filters change", async () => {
  const { account } = mount()
  await screen.findByText("Credits: 90071992547409.93 GBP")
  account("other")
  expect(
    screen.queryByText("Credits: 90071992547409.93 GBP")
  ).not.toBeInTheDocument()
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "different filters"
  )
})
