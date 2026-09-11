import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, fireEvent } from "@testing-library/react"
import { it, expect, vi, afterEach } from "vitest"
import { RequestedCoveragePanel } from "./RequestedCoveragePanel"
afterEach(() => vi.restoreAllMocks())
const params = {
  accountId: "account-a",
  startDate: "2026-02-01",
  endDate: "2026-02-28",
}
const answer = {
  case_id: "case-a",
  account_id: "account-a",
  start_date: params.startDate,
  end_date: params.endDate,
  requested_days: 28,
  available: true,
  reason: null,
  applied: false,
  limitation: "Printed bounds do not prove complete extraction.",
  periods: [],
  currencies: [
    {
      currency: "GBP",
      covered_days: 0,
      uncovered_days: 28,
      windows: [],
      gaps: [{ start: params.startDate, end: params.endDate, days: 28 }],
    },
  ],
}
function mount(data: unknown = answer) {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async () => new Response(JSON.stringify(data)))
  const client = new QueryClient()
  const element = (p = params, caseId = "case-a") => (
    <QueryClientProvider client={client}>
      <RequestedCoveragePanel caseId={caseId} params={p} />
    </QueryClientProvider>
  )
  const view = render(element())
  return {
    fetch,
    change: (p = params, caseId = "case-a") =>
      view.rerender(element(p, caseId)),
  }
}
it("checks applied dates only on request and hides results when scope changes", async () => {
  const { fetch, change } = mount()
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Check these dates" }))
  expect(await screen.findByText(/GBP: 0 of 28/)).toBeInTheDocument()
  expect(
    screen.getByText(/Missing statement dates: 2026-02-01/)
  ).toBeInTheDocument()
  change({ ...params, accountId: "other-account" })
  expect(screen.queryByText(/GBP: 0 of 28/)).not.toBeInTheDocument()
  expect(
    screen.getByRole("button", { name: "Check these dates" })
  ).toBeInTheDocument()
  expect(fetch).toHaveBeenCalledTimes(1)
})
it.each([
  { case_id: "other" },
  { account_id: "other" },
  { start_date: "2026-01-01" },
  { end_date: "2026-03-01" },
  { applied: true },
  { requested_days: 30 },
])("refuses mismatched coverage %j", async (change) => {
  mount({ ...answer, ...change })
  fireEvent.click(screen.getByRole("button", { name: "Check these dates" }))
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Coverage unavailable"
  )
  expect(screen.queryByText(/GBP: 0 of 28/)).not.toBeInTheDocument()
})
it("distinguishes unknown coverage from zero gaps", async () => {
  mount({
    ...answer,
    available: false,
    reason: "No eligible printed dates.",
    currencies: [],
  })
  fireEvent.click(screen.getByRole("button", { name: "Check these dates" }))
  expect(
    await screen.findByText(/Statement coverage could not be established/)
  ).toHaveTextContent("No eligible printed dates")
  expect(
    screen.queryByText(/Statements cover the full date range/)
  ).not.toBeInTheDocument()
})
it("does not present a fully covered range as complete transactions", async () => {
  mount({
    ...answer,
    currencies: [
      {
        ...answer.currencies[0],
        covered_days: 28,
        uncovered_days: 0,
        gaps: [],
      },
    ],
  })
  fireEvent.click(screen.getByRole("button", { name: "Check these dates" }))
  expect(await screen.findByText(/GBP: 28 of 28/)).toBeInTheDocument()
  expect(
    screen.getByText(
      /This checks statement dates, not whether every payment was extracted correctly/
    )
  ).toBeInTheDocument()
})
it("requires one account and two dates without fetching", () => {
  const { fetch, change } = mount()
  change({ ...params, endDate: "" })
  expect(
    screen.getByText(/Choose one account and enter a start and end date/)
  ).toBeInTheDocument()
  expect(fetch).not.toHaveBeenCalled()
})
