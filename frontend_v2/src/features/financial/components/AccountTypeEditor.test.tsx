import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { AccountTypeEditor } from "./AccountTypeEditor"
import { AccountTypeReview } from "./AccountTypeReview"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))

const flagged = [
  {
    transaction_id: "t1",
    date: "2024-06-05",
    description: "PAYMENT - THANK YOU",
    amount_minor: "20800",
    direction: "debit",
    proposed_direction: "credit",
  },
]
const statement = (rows = flagged, after = "liability_owed") => ({
  source_document_id: "s1",
  period_start: "2024-05-11",
  period_end: "2024-06-11",
  currency: "USD",
  convention_before: "asset_balance",
  convention_after: after,
  reconciles: false,
  reconciles_with_flagged_flipped: true,
  flagged_rows: rows,
})
const state = (overrides = {}) => ({
  case_id: "case",
  account_id: "acct",
  account_type: "",
  label: "Synthetic Holder · 4111",
  institution: "Example Bank",
  statements: [statement([], "asset_balance")],
  card_signals: ["minimum payment due", "new balance"],
  suggested_type: "credit_card",
  flagged_rows: 0,
  revision: "a".repeat(64),
  ...overrides,
})
const mount = (node: React.ReactNode) =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      {node}
    </QueryClientProvider>
  )
beforeEach(() => {
  vi.mocked(fetchAPI).mockReset()
})

it("suggests a credit card, previews, saves and flips flagged rows only when confirmed", async () => {
  let current: unknown = state()
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/type/preview"))
      return {
        case_id: "case",
        account_id: "acct",
        account_type_after: "credit_card",
        statements: [statement()],
        changed_statements: 1,
        flagged_rows: 1,
        revision: "a".repeat(64),
      } as never
    if (url.includes("/flip-rows"))
      current = state({
        account_type: "credit_card",
        suggested_type: null,
        statements: [statement([])],
      })
    else if (options?.method === "POST")
      current = state({
        account_type: "credit_card",
        suggested_type: null,
        statements: [statement()],
        flagged_rows: 1,
        revision: "b".repeat(64),
      })
    return current as never
  })
  mount(<AccountTypeEditor caseId="case" accountIds={["acct", "acct"]} />)
  expect(
    await screen.findByText(
      /This looks like a credit card: its statements print minimum payment due, new balance/
    )
  ).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Review change to credit card" })
  )
  expect(
    await screen.findByText(/1 statement will read printed balances as the amount owed/)
  ).toBeVisible()
  expect(
    screen.getByText(/1 row you entered is flagged to check \(it adds up if they are flipped\)/)
  ).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Change to credit card" }))
  expect(
    await screen.findByRole("button", { name: "Flip 1 row" })
  ).toBeVisible()
  expect(screen.getByText(/money out → money in/)).toBeVisible()
  const saveCall = vi
    .mocked(fetchAPI)
    .mock.calls.find(
      ([url, options]) =>
        url.includes("/accounts/acct/type?") && options?.method === "POST"
    )
  expect(saveCall?.[1]?.body).toMatchObject({
    account_type: "credit_card",
    expected_revision: "a".repeat(64),
  })
  // Saving the type never flips rows by itself.
  expect(
    vi.mocked(fetchAPI).mock.calls.some(([url]) => url.includes("flip-rows"))
  ).toBe(false)
  fireEvent.click(screen.getByRole("button", { name: "Flip 1 row" }))
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      expect.stringContaining("/accounts/acct/type/flip-rows"),
      expect.objectContaining({
        body: {
          source_document_id: "s1",
          transaction_ids: ["t1"],
          expected_revision: "b".repeat(64),
        },
      })
    )
  )
  expect(await screen.findByText(/Rows flipped/)).toBeVisible()
  // One account listed once even when several statements share it.
  expect(screen.getAllByText(/Synthetic Holder · 4111/)).toHaveLength(1)
})

it("offers one card recorded as two accounts for the reversible merge", async () => {
  const calls: string[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    calls.push(`${options?.method || "GET"} ${url.split("?")[0]}`)
    if (url.includes("/account-types"))
      return {
        case_id: "case",
        accounts: [
          { account_id: "a1", label: "Card A", institution: "Example Bank Card", account_type: "", statement_count: 1, card_signals: [], suggested_type: null, flagged_rows: 0 },
          { account_id: "a2", label: "Card B", institution: "Example Bank", account_type: "", statement_count: 1, card_signals: [], suggested_type: null, flagged_rows: 0 },
        ],
        same_card: [{ account_ids: ["a1", "a2"], reason: "The same full card number is printed for these accounts by the same bank." }],
      } as never
    return { case_id: "case", revision: "c".repeat(64) } as never
  })
  mount(<AccountTypeReview caseId="case" />)
  expect(
    await screen.findByText(/One card recorded as 2 accounts: Card A and Card B/)
  ).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Merge into one account" }))
  expect(await screen.findByText(/Accounts merged/)).toBeVisible()
  expect(calls).toEqual([
    "GET /api/financial/statement-import/account-types",
    "GET /api/financial/account-consolidations",
    "POST /api/financial/account-consolidations/preview",
    "POST /api/financial/account-consolidations",
    "GET /api/financial/statement-import/account-types",
  ])
})
