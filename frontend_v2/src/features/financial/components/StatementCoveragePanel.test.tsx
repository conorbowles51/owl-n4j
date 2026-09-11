import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, fireEvent } from "@testing-library/react"
import { it, expect, vi, afterEach } from "vitest"
import { StatementCoveragePanel } from "./StatementCoveragePanel"
afterEach(() => vi.restoreAllMocks())
const answer = {
  case_id: "case-a",
  offset: 0,
  has_more: false,
  applied: false,
  limitation: "No conclusion about absent transactions.",
  items: [
    {
      account_id: "account-a",
      label: "Account A",
      available: true,
      reason: null,
      periods: [],
      currencies: [
        {
          currency: "GBP",
          period_count: 2,
          covered_days: 62,
          uncovered_days: 28,
          windows: [
            { start: "2026-01-01", end: "2026-01-31", period_ids: ["j"] },
            { start: "2026-03-01", end: "2026-03-31", period_ids: ["m"] },
          ],
          gaps: [{ start: "2026-02-01", end: "2026-02-28", days: 28 }],
          overlaps: [],
        },
      ],
    },
  ],
}
function mount(data: unknown = answer, accountId?: string) {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(JSON.stringify(data)))
  render(
    <QueryClientProvider client={new QueryClient()}>
      <StatementCoveragePanel caseId="case-a" accountId={accountId} />
    </QueryClientProvider>
  )
  return fetch
}
it("loads on request and makes internal gaps and coverage limits explicit", async () => {
  const fetch = mount()
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(
    screen.getByRole("button", { name: "Check statement coverage" })
  )
  expect(
    await screen.findByText(/Missing statement dates: 2026-02-01/)
  ).toBeInTheDocument()
  expect(
    screen.getByText("No conclusion about absent transactions.")
  ).toBeInTheDocument()
  expect(fetch.mock.calls[0][1]?.method ?? "GET").toBe("GET")
})
it.each([{ case_id: "other" }, { offset: 25 }, { applied: true }])(
  "rejects mismatched coverage %j",
  async (change) => {
    mount({ ...answer, ...change })
    fireEvent.click(
      screen.getByRole("button", { name: "Check statement coverage" })
    )
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Coverage unavailable"
    )
    expect(screen.queryByText("Account A")).not.toBeInTheDocument()
  }
)
it("keeps unknown coverage distinct from no financial records", async () => {
  mount({ ...answer, items: [{ ...answer.items[0], currencies: [] }] })
  fireEvent.click(
    screen.getByRole("button", { name: "Check statement coverage" })
  )
  expect(
    await screen.findByText(
      "Statement dates are missing or cannot be used. Open the source statements to check their dates."
    )
  ).toBeInTheDocument()
})

it.each([
  { ...answer, account_id: "other" },
  {
    ...answer,
    account_id: "account-a",
    items: [{ ...answer.items[0], account_id: "other" }],
  },
])(
  "rejects a different account instead of displaying its statement dates",
  async (data) => {
    const fetch = mount(data, "account-a")
    fireEvent.click(
      screen.getByRole("button", { name: "Check statement coverage" })
    )
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "different account"
    )
    expect(String(fetch.mock.calls[0][0])).toContain("account_id=account-a")
  }
)
