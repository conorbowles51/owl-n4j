import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, useLocation } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { ReviewQueuePanel } from "./ReviewQueuePanel"
import { useBatchReview } from "../lib/batch-review-context"
import { importOutcome } from "../lib/review-queue"
import { recordStatus } from "./ImportedRecordsPanel"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true, canUpload: true }),
}))
vi.mock("./StatementImportPanel", () => ({
  StatementImportPanel: ({
    onImported,
  }: {
    onImported: (receipt: {
      case_id: string
      evidence_file_id: string
      transaction_count: number
      incomplete_count?: number
    }) => void
  }) => {
    const ctx = useBatchReview()
    return (
      <>
        <p>Focused row: {ctx?.rowId}</p>
        <p>Focused field: {ctx?.field}</p>
        <button
          onClick={() =>
            onImported({ case_id: "case", evidence_file_id: "f1", transaction_count: 12 })
          }
        >
          Import this statement
        </button>
        <button
          onClick={() =>
            onImported({
              case_id: "case",
              evidence_file_id: "f1",
              transaction_count: 10,
              incomplete_count: 2,
            })
          }
        >
          Import with held records
        </button>
      </>
    )
  },
}))

const base = {
  file_id: "f1",
  source_id: "f1",
  holder: "",
  account: "",
  institution: "",
  currency: "USD",
  can_import: false,
  status: "attention",
  bucket: "waiting",
  file_ids: ["f1"],
  other_problems: 0,
  problem_total: 1,
}
const entries = [
  {
    ...base,
    id: "i1",
    batch_id: "b1",
    statement_id: "s7",
    filename: "Card statements.pdf",
    period_start: "2020-10-08",
    period_end: "2020-11-09",
    page: 7,
    row_id: "7:0:17",
    issue: "3 rows unreadable on page 7",
    issue_reason: "reading",
    file_position: 7,
    file_statements: 54,
  },
  {
    ...base,
    id: "i2",
    batch_id: "b2",
    statement_id: "s1",
    filename: "Savings.pdf",
    period_start: "2021-01-01",
    period_end: "2021-01-31",
    issue: "Currency not printed: choose one",
    issue_reason: "currency",
    field: "holder",
    other_problems: 1,
    file_position: 1,
    file_statements: 1,
  },
]
const queue = {
  case_id: "case",
  file_ids: [],
  counts: {
    imported: 49, saving: 0, waiting: 2, ready: 3, copies: 1, unreadable: 1,
    unreadable_files: 0, rechecking: 0, left_unimported: 0, assigned: 0, unexplained: 0,
  },
  status_line: "",
  items: entries,
  copies: [{ ...base, id: "c1", batch_id: "b1", filename: "Copy.pdf", bucket: "copies", status: "duplicate_ignored", set_aside: true, copy_of: "Card statements.pdf", period_start: "", period_end: "" }],
  unreadable: [],
  unreadable_files: [],
  rechecking: [],
  ready_batches: [{ batch_id: "b1", statements: 2 }, { batch_id: "b2", statements: 1 }],
  ready: ["r1", "r2", "r3"].map((id, index) => ({
    ...base, id, batch_id: index < 2 ? "b1" : "b2", filename: `Ready ${id}.pdf`, bucket: "ready",
    status: "ready", can_import: true, period_start: "2021-01-01", period_end: "2021-01-31",
  })),
}
const batchItem = (id: string) => ({
  id,
  file_id: "f1",
  statement_id: "s7",
  status: "attention",
  filename: id === "i1" ? "Card statements.pdf" : "Savings.pdf",
  transaction_count: 3,
  source_id: "f1",
  review_revision: "a".repeat(64),
  problems: [{ message: "Check this row.", row_id: "7:0:17", page: 7 }],
})

let location = ""
function Where() {
  const current = useLocation()
  location = current.search
  return null
}

function mount(path: string, onOpenBatch = vi.fn()) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <ReviewQueuePanel caseId="case" onOpenBatch={onOpenBatch} />
        <Where />
      </MemoryRouter>
    </QueryClientProvider>
  )
  return onOpenBatch
}

beforeEach(() => {
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.includes("/review/queue")) return queue as never
    const match = url.match(/\/items\/(i\d)/)
    if (match) return batchItem(match[1]) as never
    throw Error(`unexpected ${url}`)
  })
})

it("lists only statements with something to fix, each saying what before it is opened", async () => {
  mount("/cases/case/financial?view=statements&queue=1")
  const list = await screen.findByRole("list", { name: "Statements to review" })
  const issues = list.querySelectorAll('[aria-label="Issue"]')
  // Every queue entry states its problem: none can open with nothing to fix.
  expect(issues).toHaveLength(entries.length)
  expect(issues[0]).toHaveTextContent("3 rows unreadable on page 7")
  expect(issues[1]).toHaveTextContent("Currency not printed: choose one (and 1 more check)")
  expect(screen.getByText(/statement 7 of 54 in this file/)).toBeVisible()
  expect(screen.getByLabelText("Statement status")).toHaveTextContent(
    "Imported 49 · Waiting for you 2 · Ready to save 3 · Copies set aside 1 · Couldn't read 1"
  )
  // Copies are behind their own entry, not in the queue.
  expect(screen.queryByText("Copy.pdf")).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Review copies (1)" }))
  expect(await screen.findByText(/Set aside as a copy of Card statements.pdf/)).toBeVisible()
})

it("opens the statement itself at its problem, and Next moves to the next one with issues without reloading", async () => {
  mount("/cases/case/financial?view=statements&queue=1")
  fireEvent.click((await screen.findAllByRole("button", { name: "Open" }))[0])
  expect(await screen.findByLabelText("What needs fixing")).toHaveTextContent("To fix: 3 rows unreadable on page 7")
  expect(await screen.findByText("Focused row: 7:0:17")).toBeVisible()
  expect(screen.getByText(/Statement 1 of 2 waiting for you/)).toBeVisible()
  const queueCalls = () => vi.mocked(fetchAPI).mock.calls.filter(([url]) => String(url).includes("/review/queue")).length
  const before = queueCalls()
  fireEvent.click(screen.getByRole("button", { name: "Next statement with issues (2 of 2)" }))
  await waitFor(() =>
    expect(screen.getByLabelText("What needs fixing")).toHaveTextContent("Currency not printed: choose one")
  )
  expect(location).toContain("queueItem=i2")
  expect(await screen.findByText("Focused field: holder")).toBeVisible()
  // Next was computed from the list already on screen.
  expect(queueCalls()).toBe(before)
})

it("says plainly what a save did and moves on", async () => {
  mount("/cases/case/financial?view=statements&queue=1&queueItem=i1&queueList=waiting")
  fireEvent.click(await screen.findByRole("button", { name: "Import this statement" }))
  expect(await screen.findByLabelText("Result of your last save")).toHaveTextContent(
    "Card statements.pdf (2020-10-08 to 2020-11-09): Imported: now in the ledger (12 payments)."
  )
  await waitFor(() => expect(location).toContain("queueItem=i2"))
  fireEvent.click(await screen.findByRole("button", { name: "Import with held records" }))
  expect(await screen.findByLabelText("Result of your last save")).toHaveTextContent(
    "Saved but held: 2 records are missing a value and stay outside totals (10 payments are in the ledger). One more step:"
  )
})

it("filters to selected files from their saved readings and never starts a batch", async () => {
  mount("/cases/case/financial?view=statements&queue=1&queueFiles=f1,f2")
  expect(await screen.findByText(/Showing the 2 selected files, from their saved readings/)).toBeVisible()
  const urls = vi.mocked(fetchAPI).mock.calls.map(([url]) => String(url))
  expect(urls.some((url) => url.includes("file_id=f1") && url.includes("file_id=f2"))).toBe(true)
  expect(vi.mocked(fetchAPI).mock.calls.some(([, options]) => (options as { method?: string } | undefined)?.method === "POST")).toBe(false)
})

it("saves ready statements across batches from the queue and says the result in one line", async () => {
  const posts: unknown[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url: string, options?: unknown) => {
    if (url.includes("/review/queue")) return queue as never
    if (url.includes("/review/save?")) {
      posts.push((options as { body: unknown }).body)
      return {
        request_id: "q", queued: 2,
        held: [{ item_id: "r3", filename: "Ready r3.pdf", period_start: "2021-01-01", period_end: "2021-01-31",
                 reason: "Currency not printed: choose one" }],
        operations: [{ batch_id: "b1", operation_id: "o1", queued: 2 }],
      } as never
    }
    if (url.includes("/review/save-result"))
      return { case_id: "case", found: 1, pending: 0, imported: 2, already_present: 0, duplicate_ignored: 0,
               failed: [], transaction_count: 20 } as never
    throw Error(`unexpected ${url}`)
  })
  mount("/cases/case/financial?view=statements&queue=1")
  fireEvent.click(await screen.findByRole("button", { name: "Save 3 ready statements" }))
  expect(await screen.findByLabelText("Result of saving ready statements")).toHaveTextContent(
    "2 imported, 1 held: 1 currency not printed: choose one"
  )
  // One request covers statements of both batches; no batch is opened.
  expect(posts).toHaveLength(1)
  expect((posts[0] as { item_ids: string[] }).item_ids).toEqual(["r1", "r2", "r3"])
  // The same action sits in the status line.
  expect(screen.getByRole("button", { name: "Save all 3 ready statements" })).toBeVisible()
})

it("words outcomes and record statuses plainly", () => {
  expect(importOutcome({ case_id: "c", evidence_file_id: "f", transaction_count: 1 }).message).toBe(
    "Imported: now in the ledger (1 payment)."
  )
  expect(importOutcome({ case_id: "c", evidence_file_id: "f", transaction_count: 0 }).message).toMatch(/^Imported:/)
  const held = importOutcome({ case_id: "c", evidence_file_id: "f", transaction_count: 0, incomplete_count: 1 })
  expect(held.held).toBe(true)
  expect(held.message).toMatch(/^Saved but held: 1 record is missing a value and stays outside totals\. One more step:/)
  const status = (values: Partial<Parameters<typeof recordStatus>[0]>) =>
    recordStatus({ awaiting_reconciliation: true, can_enter_now: false, missing_fields: [], ...values })
  expect(status({ awaiting_reconciliation: false, missing_fields: ["amount"] })).toBe(
    "Not in the ledger: amount missing. Open the record to fix it."
  )
  expect(status({ can_enter_now: true })).toMatch(/One click: Add to ledger/)
  expect(status({ hold_reason: "The statement doesn't add up with this row." })).toBe(
    "Saved but held outside totals: The statement doesn't add up with this row."
  )
  for (const text of [held.message, status({}), status({ can_enter_now: true })])
    expect(text).not.toContain("—")
})
