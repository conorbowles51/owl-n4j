import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { FinancialAccounts } from "./FinancialAccounts"

afterEach(() => vi.restoreAllMocks())
const account = {
  id: "a",
  holder: "Test holder",
  identifier: "001",
  institution: "Test bank",
  currency: "GBP",
}
function mount() {
  const requests: string[] = []
  const openTransactions = vi.fn()
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    const value = String(url)
    requests.push(value)
    const params = new URL(value, "http://local").searchParams
    let data: unknown
    if (value.includes("/ledger-accounts"))
      data = {
        case_id: "case",
        has_more: false,
        items: [
          account,
          { ...account, id: "b", holder: "Other holder", identifier: "002" },
        ],
      }
    else if (value.includes("/statement-checks"))
      data = {
        case_id: "case",
        account_id: params.get("account_id"),
        offset: 0,
        has_more: false,
        applied: false,
        checked_at: "2026-09-11T12:00:00Z",
        limitation: "Check only",
        items: [],
      }
    else if (value.includes("/requested-statement-coverage"))
      data = {
        case_id: "case",
        account_id: params.get("account_id"),
        start_date: params.get("start_date"),
        end_date: params.get("end_date"),
        requested_days: 28,
        available: true,
        reason: null,
        applied: false,
        limitation: "Check only",
        periods: [],
        currencies: [
          {
            currency: "GBP",
            covered_days: 0,
            uncovered_days: 28,
            windows: [],
            gaps: [
              {
                start: params.get("start_date"),
                end: params.get("end_date"),
                days: 28,
              },
            ],
          },
        ],
      }
    else if (value.includes("/statement-coverage"))
      data = {
        case_id: "case",
        account_id: params.get("account_id"),
        offset: 0,
        has_more: false,
        applied: false,
        limitation: "Check only",
        items: [],
      }
    else throw new Error(`Unexpected request: ${value}`)
    return new Response(JSON.stringify(data))
  })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const view = render(
    <QueryClientProvider client={client}>
      <FinancialAccounts caseId="case" onOpenAccount={openTransactions} />
    </QueryClientProvider>
  )
  return { ...view, requests, openTransactions }
}
it("reviews an account, checks dates and opens that account's transactions without losing the review", async () => {
  const { requests, openTransactions } = mount()
  fireEvent.click(
    (await screen.findAllByRole("button", { name: "Review statements" }))[0]
  )
  const review = screen.getByRole("region", {
    name: "Account statement review",
  })
  expect(
    within(review).getByRole("heading", { name: "Test holder · 001" })
  ).toBeVisible()
  await waitFor(() =>
    expect(requests.filter((url) => url.includes("account_id=a"))).toHaveLength(
      2
    )
  )
  fireEvent.change(within(review).getByLabelText("Statement check from"), {
    target: { value: "2026-02-01" },
  })
  fireEvent.change(within(review).getByLabelText("Statement check to"), {
    target: { value: "2026-02-28" },
  })
  fireEvent.click(
    within(review).getByRole("button", { name: "Check date range" })
  )
  expect(await within(review).findByText(/GBP: 0 of 28/)).toBeVisible()
  expect(requests.at(-1)).toContain(
    "account_id=a&start_date=2026-02-01&end_date=2026-02-28"
  )
  fireEvent.click(
    within(review).getByRole("button", {
      name: "View transactions in the checked date range",
    })
  )
  expect(openTransactions).toHaveBeenLastCalledWith("a", {
    startDate: "2026-02-01",
    endDate: "2026-02-28",
  })
  fireEvent.click(
    within(review).getByRole("button", { name: "Back to accounts" })
  )
  fireEvent.click(
    screen.getAllByRole("button", { name: "Review statements" })[0]
  )
  expect(screen.getByLabelText("Statement check from")).toHaveValue(
    "2026-02-01"
  )
  expect(screen.getByText(/GBP: 0 of 28/)).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "View all account transactions" })
  )
  expect(openTransactions).toHaveBeenLastCalledWith("a", undefined)
  fireEvent.click(screen.getByRole("button", { name: "Check date range" }))
  await waitFor(() =>
    expect(
      requests.filter((url) => url.includes("requested-statement-coverage"))
    ).toHaveLength(2)
  )
  fireEvent.click(screen.getByRole("button", { name: "Back to accounts" }))
  fireEvent.click(
    screen.getAllByRole("button", { name: "Review statements" })[1]
  )
  expect(screen.getByLabelText("Statement check from")).toHaveValue("")
  expect(screen.queryByText(/GBP: 0 of 28/)).not.toBeInTheDocument()
  await waitFor(() =>
    expect(requests.filter((url) => url.includes("account_id=b"))).toHaveLength(
      2
    )
  )
})
it("refuses reversed date ranges and labels results if draft dates change", async () => {
  const { requests } = mount()
  fireEvent.click(
    (await screen.findAllByRole("button", { name: "Review statements" }))[0]
  )
  fireEvent.change(screen.getByLabelText("Statement check from"), {
    target: { value: "2026-03-01" },
  })
  fireEvent.change(screen.getByLabelText("Statement check to"), {
    target: { value: "2026-02-28" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Check date range" }))
  expect(screen.getByRole("alert")).toHaveTextContent(
    "start date on or before the end date"
  )
  expect(
    requests.some((url) => url.includes("requested-statement-coverage"))
  ).toBe(false)
  fireEvent.change(screen.getByLabelText("Statement check from"), {
    target: { value: "2026-02-01" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Check date range" }))
  await screen.findByText(/GBP: 0 of 28/)
  fireEvent.change(screen.getByLabelText("Statement check from"), {
    target: { value: "2026-01-01" },
  })
  expect(screen.getByRole("status")).toHaveTextContent("Dates changed")
  expect(
    requests.filter((url) => url.includes("requested-statement-coverage"))
  ).toHaveLength(1)
})
