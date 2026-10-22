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
        <button onClick={() => void ctx?.save({})}>Save a field fix</button>
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
    opening_minor: "250000",
    closing_minor: "261240",
    transaction_count: 4,
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
  // Each row shows its period and printed balances, checkable against the PDF without opening it.
  expect(list.querySelectorAll('[aria-label="Period and printed balances"]')[1]).toHaveTextContent(
    "2021-01-01 to 2021-01-31 · opening 2,500.00 USD · closing 2,612.40 USD · 4 payments read"
  )
  expect(screen.getByLabelText("Statement status")).toHaveTextContent(
    "Imported 49 · Waiting for you 2 · Ready to import 3 · Copies set aside 1 · Couldn't read 1"
  )
  expect(screen.getByLabelText("Statement status")).toHaveTextContent(/^Total \d+: Imported 49/)
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
  fireEvent.click(await screen.findByRole("button", { name: "Import 3 ready statements" }))
  expect(await screen.findByLabelText("Result of importing ready statements")).toHaveTextContent(
    "2 imported, 1 held: 1 currency not printed: choose one"
  )
  // One request covers statements of both batches; no batch is opened.
  expect(posts).toHaveLength(1)
  expect((posts[0] as { item_ids: string[] }).item_ids).toEqual(["r1", "r2", "r3"])
  // One import action only, with "ready" explained next to it.
  expect(screen.getAllByRole("button", { name: /ready statements?$/ })).toHaveLength(1)
  expect(screen.getByText(/Ready means they passed every check/)).toBeVisible()
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

it("lists statements whose details were filled automatically, with each value and its source", async () => {
  const filledQueue = {
    ...queue,
    counts: { ...queue.counts, filled: 1 },
    filled: [{
      ...base, id: "f9", batch_id: "b1", filename: "Filled.pdf", bucket: "filled", period_start: "2021-02-01",
      period_end: "2021-02-28", issue: "Currency filled: USD (same account's 3 saved statements, all USD)",
      proposals: { currency: { value: "USD", label: "same account's 3 saved statements, all USD", confirmed: true } },
    }],
  }
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.includes("/review/queue")) return filledQueue as never
    throw Error(`unexpected ${url}`)
  })
  mount("/cases/case/financial?view=statements&queue=1")
  fireEvent.click(await screen.findByRole("button", { name: "Details filled automatically 1" }))
  expect(await screen.findByText("Filled.pdf")).toBeVisible()
  expect(screen.getByLabelText("Details found automatically")).toHaveTextContent(
    "Fills currency: USD (same account's 3 saved statements, all USD)"
  )
  expect(screen.getByRole("button", { name: "Open to change" })).toBeVisible()
  expect(screen.getByRole("button", { name: "Import 3 ready, and 1 once its details are filled" })).toBeVisible()
})

it("shows every blocker after the summary sentence", async () => {
  const withAlso = {
    ...queue,
    items: [{ ...entries[0], also: ["Account number not found: enter it", "Account holder not found: enter it"] }, entries[1]],
  }
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.includes("/review/queue")) return withAlso as never
    throw Error(`unexpected ${url}`)
  })
  mount("/cases/case/financial?view=statements&queue=1")
  expect((await screen.findAllByLabelText("Also to fix"))[0]).toHaveTextContent(
    "also: Account number not found: enter it; Account holder not found: enter it"
  )
})

it("collapses a file the reader cannot handle yet into one line outside the waiting list", async () => {
  const reader = {
    ...queue,
    counts: { ...queue.counts, reader_fix: 2 },
    reader_fix: [0, 1].map((n) => ({ ...base, id: `x${n}`, batch_id: "b1", filename: "Subpoena.pdf", bucket: "reader_fix",
      period_start: "", period_end: "", issue: "Currency not printed: choose one", also: ["Account number not found: enter it"] })),
    reader_files: [{ file_id: "f9", filename: "Subpoena.pdf", batch_id: "b1", statements: 2, file_statements: 3,
      item_ids: ["x0", "x1"], message: "Loupe can't read this file reliably yet (2 statements). No need to review it by hand; it will be re-read when the reader is fixed." }],
  }
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.includes("/review/queue")) return reader as never
    throw Error(`unexpected ${url}`)
  })
  mount("/cases/case/financial?view=statements&queue=1")
  expect(await screen.findByLabelText("Statement status")).toHaveTextContent("Waiting for a reader fix 2")
  expect(screen.queryByText("Subpoena.pdf")).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Waiting for a reader fix (2 in 1 file)" }))
  expect(await screen.findByText(/Loupe can't read this file reliably yet \(2 statements\)/)).toBeVisible()
  expect(screen.getByText("Show their 2 statements")).toBeVisible()
})

it("never counts files removed from Financial as couldn't read, and says what they are", async () => {
  const removed = {
    ...queue,
    counts: { ...queue.counts, unreadable: 0, unreadable_files: 1, removed_files: 2, copy_files: 0 },
    unreadable_files: [{ batch_id: "b1", source_id: "f5", file_id: "f5", filename: "Scan.pdf", message: "PDF source preparation failed." }],
    set_aside_files: ["f6", "f7"].map((id) => ({
      batch_id: "b3", source_id: id, file_id: id, filename: `Removed ${id}.pdf`, reason: "removed",
      message: "You removed this file from Financial, so it is not read. If it should be read, restore it under Removed files in Statements & accounts.",
    })),
  }
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.includes("/review/queue")) return removed as never
    throw Error(`unexpected ${url}`)
  })
  mount("/cases/case/financial?view=statements&queue=1&queueList=unreadable")
  const status = await screen.findByLabelText("Statement status")
  expect(status).toHaveTextContent("Couldn't read 1")
  expect(status).toHaveTextContent("Files removed from Financial 2")
  expect(await screen.findByText(/Scan.pdf: PDF source preparation failed/)).toBeVisible()
  expect(screen.getByText(/2 files are not counted as couldn't read/)).toBeVisible()
  fireEvent.click(screen.getByText(/2 files are not counted as couldn't read/))
  expect(screen.getByText(/Removed f6.pdf: You removed this file from Financial/)).toBeVisible()
})

it("after a fix inside a statement, refreshes the queue and its totals and says where the statement stands", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url: string, options?: unknown) => {
    if (url.includes("/review/queue")) return queue as never
    if ((options as { method?: string } | undefined)?.method === "PUT")
      return { status: "attention", review_revision: "b".repeat(64) } as never
    const match = url.match(/\/items\/(i\d)/)
    if (match) return batchItem(match[1]) as never
    return {} as never
  })
  mount("/cases/case/financial?view=statements&queue=1&queueItem=i1&queueList=waiting")
  const queueCalls = () => vi.mocked(fetchAPI).mock.calls.filter(([url]) => String(url).includes("/review/queue")).length
  fireEvent.click(await screen.findByRole("button", { name: "Save a field fix" }))
  const before = queueCalls()
  expect(await screen.findByLabelText("Result of your last save")).toHaveTextContent(
    "Card statements.pdf (2020-10-08 to 2020-11-09): Saved. Still needs: 3 rows unreadable on page 7."
  )
  expect(queueCalls()).toBeGreaterThanOrEqual(before)
  expect(vi.mocked(fetchAPI).mock.calls.filter(([url]) => String(url).includes("/review/queue")).length).toBeGreaterThan(1)
})

it("loads the next statement in the background so Next shows it without waiting for the server", async () => {
  mount("/cases/case/financial?view=statements&queue=1&queueItem=i1&queueList=waiting")
  const itemCalls = (id: string) =>
    vi.mocked(fetchAPI).mock.calls.filter(([url]) => String(url).includes(`/items/${id}?`)).length
  expect(await screen.findByLabelText("What needs fixing")).toHaveTextContent("3 rows unreadable on page 7")
  await waitFor(() => expect(itemCalls("i2")).toBe(1))
  fireEvent.click(screen.getByRole("button", { name: "Next statement with issues (2 of 2)" }))
  await waitFor(() =>
    expect(screen.getByLabelText("What needs fixing")).toHaveTextContent("Currency not printed: choose one")
  )
  expect(itemCalls("i2")).toBe(1)
})

it("lists failed readings of a file that another upload read as copies of that upload", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.includes("/review/queue"))
      return {
        ...queue,
        counts: { ...queue.counts, copies: 4, copy_files: 2 },
        copies: [
          ...queue.copies,
          { ...queue.copies[0], id: "c2", filename: "Month.pdf", status: "attention", copy_of: "Month.pdf",
            copy_reason: "same_file_read" },
          { ...queue.copies[0], id: "c3", filename: "Month resaved.pdf", status: "attention", copy_of: "Month.pdf",
            copy_reason: "same_pages_read" },
        ],
        copy_files: [
          { batch_id: "b2", source_id: "f9", file_id: "f9", filename: "Month (2).pdf", message: "x", copy_of: "Month.pdf" },
          { batch_id: "b2", source_id: "f8", file_id: "f8", filename: "Month printed.pdf", message: "x", copy_of: "Month.pdf",
            copy_reason: "same_pages_read" },
        ],
      } as never
    throw Error(`unexpected ${url}`)
  })
  const onOpenBatch = mount("/cases/case/financial?view=statements&queue=1")
  fireEvent.click(await screen.findByRole("button", { name: "Review copies (3)" }))
  expect(await screen.findByText(/Same file as Month.pdf, which was read. This upload's own reading is not used/)).toBeVisible()
  expect(screen.getByText("Files set aside as copies")).toBeVisible()
  expect(screen.getByText(/Month \(2\).pdf: same file as Month.pdf, which was read/)).toBeVisible()
  expect(screen.getByText(/Every page is the same as Month.pdf, which was read. This upload's own reading/)).toBeVisible()
  expect(screen.getByText(/Month printed.pdf: every page is the same as Month.pdf, which was read/)).toBeVisible()
  fireEvent.click(screen.getAllByRole("button", { name: "Open its batch" })[0])
  expect(onOpenBatch).toHaveBeenCalledWith("b2")
})

it("reads removed PDFs whose restart copy is gone afresh with one explicit request", async () => {
  const files = [
    { batch_id: "b3", source_id: "s1", file_id: "s1", filename: "A.pdf", message: "The source recorded…", read_afresh_revision: "r1" },
    { batch_id: "b3", source_id: "s2", file_id: "s2", filename: "B.pdf", message: "The source recorded…", read_afresh_revision: "r2" },
    { batch_id: "b3", source_id: "s3", file_id: "s3", filename: "C.pdf", message: "PDF source preparation failed" },
  ]
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.includes("/review/queue"))
      return { ...queue, counts: { ...queue.counts, unreadable_files: 3 }, unreadable_files: files } as never
    if (url.includes("/review/read-afresh"))
      return { requested: 2, queued: 1, already: 0, refused: [{ batch_id: "b3", source_id: "s2", message: "The source changed." }] } as never
    throw Error(`unexpected ${url}`)
  })
  mount("/cases/case/financial?view=statements&queue=1&queueList=unreadable")
  fireEvent.click(await screen.findByRole("button", { name: "Read 2 PDFs afresh" }))
  expect(await screen.findByText("1 PDF is being read afresh; 1 not started: The source changed.")).toBeVisible()
  const call = vi.mocked(fetchAPI).mock.calls.find(([url]) => String(url).includes("/review/read-afresh"))
  expect(call?.[1]).toMatchObject({
    method: "POST",
    body: { files: [
      { batch_id: "b3", source_id: "s1", expected_revision: "r1" },
      { batch_id: "b3", source_id: "s2", expected_revision: "r2" },
    ] },
  })
})

it("checks the unreadable statements' files again with the current reader in one request", async () => {
  const unreadable = [
    { ...base, id: "u1", batch_id: "b1", file_id: "f1", filename: "A.pdf", bucket: "unreadable", status: "attention" },
    { ...base, id: "u2", batch_id: "b2", file_id: "f2", filename: "B.pdf", bucket: "unreadable", status: "attention" },
  ]
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.includes("/review/queue"))
      return { ...queue, counts: { ...queue.counts, unreadable: 2 }, unreadable } as never
    if (url.includes("/review/check-again")) return { requested: 2, queued: 2, skipped: [] } as never
    throw Error(`unexpected ${url}`)
  })
  mount("/cases/case/financial?view=statements&queue=1&queueList=unreadable")
  fireEvent.click(await screen.findByRole("button", { name: "Check 2 statements again" }))
  expect(await screen.findByText("2 files are being checked again")).toBeVisible()
  const call = vi.mocked(fetchAPI).mock.calls.find(([url]) => String(url).includes("/review/check-again"))
  expect(call?.[1]).toMatchObject({
    method: "POST",
    body: { files: [{ batch_id: "b1", file_id: "f1" }, { batch_id: "b2", file_id: "f2" }] },
  })
})

it("accounts for every statement it counted as ready: imported, held, still importing or not ready after filling", async () => {
  const filledEntry = {
    ...base, id: "f9", batch_id: "b1", filename: "Filled.pdf", bucket: "filled", period_start: "2021-02-01",
    period_end: "2021-02-28", proposals: { currency: { value: "USD", label: "same account", confirmed: true } },
  }
  let after = false
  const before = { ...queue, counts: { ...queue.counts, ready: 1, filled: 4 }, ready: queue.ready.slice(0, 1),
    filled: [1, 2, 3, 4].map((n) => ({ ...filledEntry, id: `f${n}`, filename: `Filled ${n}.pdf` })) }
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.includes("/review/queue"))
      return (after
        ? { ...queue, ready: [], items: [1, 2, 3].map((n) => ({ ...entries[1], id: `f${n}`, filename: `Filled ${n}.pdf`,
            issue: "Account number not found: enter it" })) }
        : before) as never
    if (url.includes("/review/fill"))
      return { case_id: "case", filled: 4, statements: 4, failed: 0, ready_item_ids: ["f4"] } as never
    if (url.includes("/review/save?"))
      return { request_id: "q", queued: 2, held: [], operations: [{ batch_id: "b1", operation_id: "o1", queued: 2 }] } as never
    if (url.includes("/review/save-result")) {
      after = true
      return { case_id: "case", found: 1, pending: 0, imported: 1, already_present: 0, duplicate_ignored: 1,
               failed: [], transaction_count: 3 } as never
    }
    throw Error(`unexpected ${url}`)
  })
  mount("/cases/case/financial?view=statements&queue=1")
  // The button never claims five statements will be imported.
  fireEvent.click(await screen.findByRole("button", { name: "Import 1 ready, and 4 once their details are filled" }))
  const result = await screen.findByLabelText("Result of importing ready statements")
  expect(result).toHaveTextContent(
    "Of 5 counted as ready: 1 imported, 1 held: 1 set aside as a copy of another statement, 3 not imported: details filled, but they still need something"
  )
  fireEvent.click(screen.getByText("Which 3 were not imported after filling their details"))
  await waitFor(() =>
    expect(screen.getByLabelText("Not ready after filling")).toHaveTextContent(
      "Filled 1.pdf (2021-02-01 to 2021-02-28): still needs: Account number not found: enter it"
    )
  )
  fireEvent.click(screen.getByText("Which 1 statement was held"))
  expect(screen.getByText(/1 without a file name in the server's answer: 1 set aside as a copy/)).toBeVisible()
})
