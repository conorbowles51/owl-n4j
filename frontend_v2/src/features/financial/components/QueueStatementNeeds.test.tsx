import { fireEvent, render, screen, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { ReviewQueuePanel } from "./ReviewQueuePanel"

vi.mock("@/lib/api-client", async (actual) => ({
  ...(await actual<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true, canUpload: true }),
}))

const GATE = "Enter at least one printed opening or closing balance to save a statement without transactions."
// CommitmentLetter (3).pdf in OPDMD66: bank, holder and currency read; no dates, balances, account or payments.
const letter = {
  id: "i1", batch_id: "b1", file_id: "f1", file_ids: ["f1"], source_id: "f1", statement_id: null,
  filename: "CommitmentLetter (3).pdf", holder: "Keny V Alvarado Gomez", account: "", institution: "Truist Bank",
  currency: "USD", period_start: "", period_end: "", page: 1, can_import: false, status: "attention", bucket: "waiting",
  file_position: 1, file_statements: 1, other_problems: 0, problem_total: 1, issue: GATE, issue_reason: "reading",
  reasons: ["reading"], issue_messages: [GATE], opening_minor: null, closing_minor: null, transaction_count: 0,
}
const counts = { imported: 0, saving: 0, waiting: 1, ready: 0, filled: 0, copies: 0, unreadable: 0, unreadable_files: 0,
  rechecking: 0, left_unimported: 0, assigned: 0, unexplained: 0 }
let left = false
let sent: { url: string; body?: unknown }[] = []
beforeEach(() => {
  left = false
  sent = []
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url: string, options?: { method?: string; body?: unknown }) => {
    sent.push({ url, body: options?.body })
    if (url.includes("/review/queue"))
      return { case_id: "case", file_ids: [], counts: left ? { ...counts, waiting: 0, left_unimported: 1 } : counts,
        status_line: "", items: left ? [] : [letter], ready: [], copies: [], unreadable: [], unreadable_files: [],
        rechecking: [] } as never
    if (url.includes("/import-choice")) {
      left = true
      return { status: "skipped" } as never
    }
    if (url.includes("/batches/b1/items/i1"))
      return { id: "i1", file_id: "f1", statement_id: null, status: "attention", filename: letter.filename,
        transaction_count: 0, source_id: "f1", review_revision: "a".repeat(64), disposition_revision: "d".repeat(64),
        problems: [{ message: GATE, row_id: null }] } as never
    throw Error(`unexpected ${url}`)
  })
})

const mount = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/cases/case/financial?view=statements&queue=1"]}>
        <ReviewQueuePanel caseId="case" onOpenBatch={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>
  )

it("lists every required detail at once and what is already there, and offers This isn't a statement", async () => {
  mount()
  const item = (await screen.findByText("No payments and no balances were read from this statement")).closest("li")!
  const needs = within(item).getByLabelText("Before it can be imported")
  const missing = within(needs).getByRole("list", { name: "Required details still missing" })
  expect(within(missing).getAllByRole("listitem").map((chip) => chip.textContent)).toEqual([
    "opening balance Required: to check the payments add up",
    "closing balance Required: to check the payments add up",
    "statement start date Required: to know which dates it covers (or confirm none is printed)",
    "statement end date Required: to know which dates it covers",
    "account number Required: to know which account it belongs to",
    "confirmation that the period had no payments Required: no payments were read; check every page first",
  ])
  expect(needs).toHaveTextContent("Already there: account holder, bank and currency.")
  expect(needs).toHaveTextContent("Optional: printed totals of money in and out (only if the statement prints them).")

  fireEvent.click(within(item).getByRole("button", { name: "This isn't a statement" }))
  const reason = await within(item).findByLabelText("Reason to leave it out: not a statement")
  const confirm = within(item).getByRole("button", { name: "Leave it out: not a statement" })
  expect(confirm).toBeDisabled()
  fireEvent.change(reason, { target: { value: "A loan commitment letter, not a statement" } })
  fireEvent.click(confirm)
  expect(await screen.findByLabelText("Result of your last save")).toHaveTextContent(
    "CommitmentLetter (3).pdf (dates not read): Left out of the import: not a statement."
  )
  const choice = sent.find((call) => call.url.includes("/import-choice"))!
  expect(choice.url).toContain("/batches/b1/items/i1/import-choice?case_id=case")
  expect(choice.body).toEqual({ action: "skip", reason: "A loan commitment letter, not a statement", expected_revision: "d".repeat(64) })
})
