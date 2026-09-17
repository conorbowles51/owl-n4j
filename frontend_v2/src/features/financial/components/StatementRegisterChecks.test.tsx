import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, within } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { StatementRegisterChecks } from "./StatementRegisterChecks"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("./AccountStatementReview", () => ({
  AccountStatementReview: ({
    account,
    datesFirst,
    onOpenTransactions,
  }: {
    account: { id: string }
    datesFirst: boolean
    onOpenTransactions: (dates: { startDate: string; endDate: string }) => void
  }) => (
    <div>
      Review {account.id}, dates first: {String(datesFirst)}
      <button
        onClick={() =>
          onOpenTransactions({ startDate: "2026-02-01", endDate: "2026-02-28" })
        }
      >
        Open checked payments
      </button>
    </div>
  ),
}))
vi.mock("./DuplicateCandidatesPanel", () => ({
  DuplicateCandidatesPanel: ({
    autoLoad,
    showCrossCase,
  }: {
    autoLoad: boolean
    showCrossCase: boolean
  }) => (
    <p>
      Duplicate review loaded: {String(autoLoad)}, other cases:{" "}
      {String(showCrossCase)}
    </p>
  ),
}))
afterEach(() => vi.resetAllMocks())
const period = {
  period_id: "jan",
  source_document_id: "doc-jan",
  evidence_file_id: "file-jan",
  filename: "January.pdf",
  currency: "EUR",
  start: "2026-01-01",
  end: "2026-01-31",
  included: true,
  exclusion_reason: null,
}
const account = {
  account_id: "account-a",
  label: "TEST-A",
  holder: "Example Company",
  identifier: "TEST-A",
  institution: "Example Bank",
  currency: "EUR",
  available: true,
  reason: null,
  periods: [period],
  currencies: [
    {
      currency: "EUR",
      period_count: 3,
      covered_days: 62,
      uncovered_days: 28,
      windows: [
        { start: "2026-01-01", end: "2026-01-31", period_ids: ["jan"] },
        { start: "2026-03-01", end: "2026-03-31", period_ids: ["mar", "copy"] },
      ],
      gaps: [{ start: "2026-02-01", end: "2026-02-28", days: 28 }],
      overlaps: [{ period_id: "copy", start: "2026-03-01", end: "2026-03-31" }],
    },
  ],
}
const answer = {
  case_id: "case-a",
  account_id: null,
  offset: 0,
  has_more: false,
  applied: false,
  limitation: "Printed dates only",
  items: [account],
}
function mount(data: unknown = answer) {
  vi.mocked(fetchAPI).mockResolvedValue(data)
  const onOpenTransactions = vi.fn()
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <StatementRegisterChecks
        caseId="case-a"
        onOpenTransactions={onOpenTransactions}
      />
    </QueryClientProvider>
  )
  return onOpenTransactions
}
it("shows gaps and overlaps without a separate manual load, then opens the correct account and date scope", async () => {
  const open = mount()
  expect(await screen.findByText("Missing statement dates")).toBeInTheDocument()
  expect(
    screen.getByText("2026-02-01 to 2026-02-28 · 28 days · EUR")
  ).toBeInTheDocument()
  expect(screen.getByText(/1 overlapping statement period/)).toBeInTheDocument()
  expect(
    screen.getByText(/Files still being reviewed are not counted yet/)
  ).toBeInTheDocument()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Review dates for Example Company · TEST-A",
    })
  )
  expect(
    within(screen.getByRole("dialog")).getByText(
      /Review account-a, dates first: true/
    )
  ).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Open checked payments" }))
  expect(open).toHaveBeenCalledWith("account-a", {
    startDate: "2026-02-01",
    endDate: "2026-02-28",
  })
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
})
it("loads duplicate review from the register without asking for another load click", async () => {
  mount()
  await screen.findByText("Missing statement dates")
  fireEvent.click(
    screen.getByRole("button", { name: "Check duplicate imports" })
  )
  expect(
    within(screen.getByRole("dialog")).getByText(
      "Duplicate review loaded: true, other cases: false"
    )
  ).toBeInTheDocument()
})
it.each([
  { case_id: "other" },
  { offset: 25 },
  { account_id: "other" },
  { applied: true },
])("rejects a mismatched response %j", async (change) => {
  mount({ ...answer, ...change })
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Statement dates could not be checked"
  )
  expect(screen.queryByText("Example Company · TEST-A")).not.toBeInTheDocument()
})
it("does not describe unavailable or incomplete dates as having no gaps", async () => {
  mount({
    ...answer,
    items: [
      {
        ...account,
        available: false,
        reason: "Too many periods to calculate this account.",
        currencies: [],
        periods: [],
      },
      {
        ...account,
        account_id: "account-b",
        label: "B",
        currencies: [],
        periods: [
          { ...period, included: false, exclusion_reason: "missing_dates" },
        ],
      },
    ],
  })
  expect(
    await screen.findByText("Too many periods to calculate this account.")
  ).toBeInTheDocument()
  expect(screen.getByText(/coverage is unknown/)).toBeInTheDocument()
  expect(screen.getByText(/1 statement period has missing/)).toBeInTheDocument()
  expect(
    screen.queryByText(/No gaps or overlaps between/)
  ).not.toBeInTheDocument()
})
it("keeps page counts explicit and clears stale results on a failed next page", async () => {
  mount({ ...answer, has_more: true })
  expect(
    await screen.findByText(/Counts cover the accounts on this page/)
  ).toBeInTheDocument()
  vi.mocked(fetchAPI).mockRejectedValueOnce(new Error("Page unavailable"))
  fireEvent.click(screen.getByRole("button", { name: "Next accounts" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("Page unavailable")
  expect(screen.queryByText("Example Company · TEST-A")).not.toBeInTheDocument()
  expect(screen.getByText("Account page 2")).toBeInTheDocument()
  expect(
    screen.getByRole("button", { name: "Previous accounts" })
  ).not.toBeDisabled()
})
