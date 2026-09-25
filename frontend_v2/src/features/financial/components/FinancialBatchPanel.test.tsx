import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, useLocation } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { FinancialBatchPanel } from "./FinancialBatchPanel"
import { useBatchReview } from "../lib/batch-review-context"
import { useInvestigationScopeStore } from "../stores/investigation-scope"
import {
  useFinancialDraftStore,
  financialDraftKey,
} from "../stores/financial-drafts"
import { paymentTableDraftName } from "../lib/payment-table-draft"
import { useFinancialStore } from "../stores/financial.store"
import { useStatementWorkspace } from "../stores/statement-workspace"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true, canUpload: true }),
}))
vi.mock("./StatementImportPanel", () => ({
  StatementImportPanel: ({
    onImported,
  }: {
    onImported: (receipt: {
      transaction_count: number
      record_count: number
    }) => void
  }) => {
    const ctx = useBatchReview()
    return (
      <>
        <p>Focused row: {ctx?.rowId}</p>
        <p>Saved holder: {ctx?.draft?.holder}</p>
        <p>Focused field: {ctx?.field}</p>
        <button
          onClick={() => onImported({ transaction_count: 0, record_count: 0 })}
        >
          Complete balance-only import
        </button>
        <button
          onClick={async () => {
            await ctx!.save({ checked: true })
            ctx!.saved()
          }}
        >
          Save for bulk import
        </button>
      </>
    )
  },
}))
const item = {
  id: "item",
  file_id: "file",
  statement_id: "period",
  filename: "Checking.pdf",
  status: "attention",
  currency: "EUR",
  transaction_count: 3,
  source_id: "file",
  problems: [{ message: "Check the payment date.", row_id: "1:0:2", page: 1 }],
}
const batch = {
  id: "batch",
  case_id: "case",
  status: "review",
  files: [
    {
      source_id: "file",
      file_id: "file",
      filename: "Checking.pdf",
      status: "checked",
    },
  ],
  counts: { ready: 2, attention: 1, imported: 0 },
  ready_transactions: 14,
  ready_revision: "a".repeat(64),
  total: 1,
  items: [item],
}
function Location() {
  const location = useLocation()
  return <output aria-label="Location">{location.search}</output>
}
function mount(entry = "/cases/case/financial?view=statements&batch=batch") {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <MemoryRouter initialEntries={[entry]}>
        <FinancialBatchPanel caseId="case" />
        <Location />
      </MemoryRouter>
    </QueryClientProvider>
  )
}
beforeEach(() => {
  useStatementWorkspace.setState({ selections: {}, reviewChoices: {} })
  useFinancialDraftStore.setState({ drafts: {} })
  vi.resetAllMocks()
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method)
      return {
        saved: true,
        status: "ready",
        review_revision: "c".repeat(64),
      } as never
    if (url.includes("/items/"))
      return {
        ...item,
        review_revision: "b".repeat(64),
        review_request: {
          expected_revision: "a".repeat(64),
          holder: "Checked owner",
          account_number: "123",
          institution: "Bank",
          period_start: "2023-01-01",
          period_end: "2023-01-31",
          details_reason: "Checked",
          rows: [],
        },
      } as never
    return batch as never
  })
})

it("explains an unavailable source and opens Evidence without an endless Retry prompt", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({
    ...batch,
    files: [
      {
        ...batch.files[0],
        status: "error",
        review_file_id: null,
        error: "The original is unavailable in this case.",
        recovery: {
          action: "source_unavailable",
          stage: "source_unavailable",
          message:
            "Restore the source in Evidence or select the correct source.",
          review_file_id: null,
        },
      },
    ],
  } as never)
  mount()
  expect(
    await screen.findByText(
      "Restore the source in Evidence or select the correct source."
    )
  ).toBeVisible()
  expect(
    screen.getByRole("button", { name: "Open file review" })
  ).toBeDisabled()
  expect(screen.queryByRole("button", { name: "Retry this file" })).toBeNull()
  expect(
    screen.getByRole("button", { name: "Check source again" })
  ).toBeEnabled()
  expect(
    screen.getByRole("link", { name: "Find source in Evidence" })
  ).toHaveAttribute("href", "/cases/case/evidence")
})

it("keeps a blocked statement reviewable when no admission calculation is available", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({
    ...batch,
    items: [
      {
        ...item,
        admission: null,
        can_import: false,
        problems: [
          { message: "Choose the printed currency.", field: "currency" },
        ],
      },
    ],
  } as never)
  mount()
  expect(await screen.findByText("Choose the printed currency.")).toBeVisible()
  expect(screen.getByRole("button", { name: "Open file review" })).toBeEnabled()
})

it("opens the recovered file in Statement files and preserves the originating batch filter", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({
    ...batch,
    files: [
      {
        ...batch.files[0],
        review_file_id: "older-file",
        recovery: { review_file_id: "recovered-file" },
      },
    ],
  } as never)
  mount("/cases/case/financial?view=statements&batch=batch&batchCheck=balance")
  fireEvent.click(
    await screen.findByRole("button", { name: "Open file review" })
  )
  const destination = new URLSearchParams(
    screen.getByLabelText("Location").textContent || ""
  )
  expect(destination.get("files")).toBe("1")
  expect(destination.get("reviewFile")).toBe("recovered-file")
  expect(destination.get("returnBatch")).toBe("batch")
  expect(destination.get("returnBatchCheck")).toBe("balance")
  expect(destination.has("batch")).toBe(false)
  expect(
    Object.values(useStatementWorkspace.getState().selections)
  ).toContainEqual({ fileId: "recovered-file", open: true })
})

it("Back to all statements opens the file register rather than the batch list or a stale review", async () => {
  useStatementWorkspace.getState().select("anonymous:case", "unfinished-file")
  mount()
  fireEvent.click(
    await screen.findByRole("button", { name: "Back to all statements" })
  )
  const destination = new URLSearchParams(
    screen.getByLabelText("Location").textContent || ""
  )
  expect(destination.get("files")).toBe("1")
  expect(destination.has("batch")).toBe(false)
  expect(destination.has("reviewFile")).toBe(false)
  expect(destination.has("returnBatch")).toBe(false)
  expect(useStatementWorkspace.getState().selections["anonymous:case"]).toEqual(
    { fileId: "unfinished-file", open: false }
  )
})
it("filters by the whole-batch reason, focuses the right detail, and retains the reason through review navigation", async () => {
  const original = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/next-statement?"))
      return {
        case_id: "case",
        batch_id: "batch",
        item_id: "next",
        position: 2,
        total: 201,
      } as never
    if (url.includes("/items/"))
      return {
        ...item,
        id: url.includes("/next?") ? "next" : "item",
        review_revision: "b".repeat(64),
        problems: [
          {
            message: "Check this payment",
            row_id: "1:0:2",
            review_reason: "reading",
          },
          {
            message: "The account holder has not been identified.",
            field: "holder",
            kind: "statement_detail",
            review_reason: "holder",
          },
        ],
      } as never
    if (!options?.method) {
      const filter = new URL(url, "http://localhost").searchParams.get(
        "review_group"
      )
      return {
        ...batch,
        total: filter ? 201 : 202,
        review_group: filter,
        review_group_label: filter ? "Missing account holder" : null,
        review_summary: {
          blocked_statements: 1,
          importable_with_checks: 201,
          imported_with_checks: 0,
          unchecked_balance_statements: 30,
          groups: [
            {
              id: "holder",
              label: "Missing account holder",
              explanation: "Add the holder printed on the statement.",
              statement_count: 201,
              check_count: 201,
              blocked_statements: 0,
              importable_statements: 201,
              imported_statements: 0,
            },
          ],
        },
        items: [
          {
            ...item,
            problems: [
              {
                message: "Check this payment",
                row_id: "1:0:2",
                review_reason: "reading",
              },
              {
                message: "The account holder has not been identified.",
                field: "holder",
                kind: "statement_detail",
                review_reason: "holder",
              },
            ],
          },
        ],
      } as never
    }
    return original(url, options)
  })
  mount()
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Show statements: Missing account holder",
    })
  )
  await waitFor(() =>
    expect(
      screen.getByRole("heading", {
        name: "Statements: Missing account holder",
      })
    ).toHaveFocus()
  )
  expect(screen.getByText("1–100 of 201")).toBeVisible()
  expect(
    screen.getByText(/This action covers all ready statements/)
  ).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Review problems" }))
  await screen.findByText("Focused field: holder")
  expect(screen.getByLabelText("Location").textContent).toContain(
    "batchCheck=holder"
  )
  expect(screen.getByLabelText("Location").textContent).not.toContain(
    "batchRow="
  )
  fireEvent.click(screen.getByRole("button", { name: "Next statement" }))
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      expect.stringContaining(
        "/next-statement?case_id=case&direction=next&review_group=holder"
      )
    )
  )
  await waitFor(() =>
    expect(screen.getByLabelText("Location").textContent).toContain(
      "batchItem=next"
    )
  )
  fireEvent.click(screen.getByRole("button", { name: "Back to bulk import" }))
  fireEvent.click(
    await screen.findByRole("button", { name: "Clear reason filter" })
  )
  await screen.findByRole("heading", { name: "Statements in this batch" })
  expect(screen.getByLabelText("Location").textContent).not.toContain(
    "batchCheck="
  )
  expect(
    vi.mocked(fetchAPI).mock.calls.some(([url]) => url.includes("/confirm?"))
  ).toBe(false)
})
it("returns to an existing page when corrections remove the last page of matching statements", async () => {
  let total = 101
  vi.mocked(fetchAPI).mockImplementation(
    async () => ({ ...batch, total }) as never
  )
  mount()
  fireEvent.click(
    await screen.findByRole("button", { name: "Next statements" })
  )
  await screen.findByText("101–101 of 101")
  total = 100
  fireEvent.click(screen.getByRole("button", { name: "Refresh batch" }))
  await screen.findByText("1–100 of 100")
  expect(
    screen.getByRole("button", { name: "Previous statements" })
  ).toBeDisabled()
})
it("submits without randomUUID and checks the retained request after a lost response", async () => {
  const random = Object.getOwnPropertyDescriptor(
    globalThis.crypto,
    "randomUUID"
  )
  Object.defineProperty(globalThis.crypto, "randomUUID", {
    configurable: true,
    value: undefined,
  })
  let requestId = ""
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/confirm?")) {
      requestId = (options?.body as { request_id: string }).request_id
      throw Error("Connection interrupted")
    }
    if (url.includes("/operations/"))
      return {
        case_id: "case",
        batch_id: "batch",
        request_id: requestId,
        operation: {
          id: requestId,
          status: "complete",
          created_at: "2026-01-01T00:00:00Z",
          statement_count: 2,
          pending: 0,
          failed: 0,
          imported: 2,
          already_present: 0,
          transaction_count: 14,
          incomplete_count: 0,
          outcomes: [],
        },
      } as never
    return batch as never
  })
  try {
    const view = mount()
    fireEvent.click(
      await screen.findByRole("button", { name: "Import 14 transactions" })
    )
    await screen.findByText("Connection interrupted")
    expect(requestId).toMatch(/^[0-9a-f-]{36}$/)
    view.unmount()
    mount()
    fireEvent.click(
      await screen.findByRole("button", { name: "Check import result" })
    )
    expect(
      await screen.findByText(
        /Import complete: 2 imported.*14 transactions saved/
      )
    ).toBeVisible()
    expect(
      vi
        .mocked(fetchAPI)
        .mock.calls.filter(([url]) => url.includes("/confirm?")).length
    ).toBe(1)
  } finally {
    if (random) Object.defineProperty(globalThis.crypto, "randomUUID", random)
    else Reflect.deleteProperty(globalThis.crypto, "randomUUID")
  }
})

it("reports an absent receipt and retries the same submission rather than guessing success", async () => {
  const requests: string[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/confirm?")) {
      requests.push((options?.body as { request_id: string }).request_id)
      throw Error("Network unavailable")
    }
    if (url.includes("/operations/"))
      return {
        case_id: "case",
        batch_id: "batch",
        request_id: requests[0],
        operation: null,
      } as never
    return batch as never
  })
  mount()
  fireEvent.click(
    await screen.findByRole("button", { name: "Import 14 transactions" })
  )
  await screen.findByText("Network unavailable")
  fireEvent.click(screen.getByRole("button", { name: "Check import result" }))
  await screen.findByText(/No accepted import was found/)
  fireEvent.click(
    screen.getByRole("button", { name: "Import 14 transactions" })
  )
  await waitFor(() => expect(requests).toHaveLength(2))
  expect(requests[1]).toBe(requests[0])
})
it("distinguishes repeated file runs and opens the selected saved batch", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) => {
    if (url.includes("/list?"))
      return {
        case_id: "case",
        batches: [
          {
            id: "latest-run",
            status: "preparing",
            created_at: "2026-09-20T17:00:00Z",
            file_count: 588,
            created_by: "Alex",
            checked_files: 587,
            failed_files: 1,
            filenames: ["Checking EUR.pdf"],
          },
          {
            id: "earlier-run",
            status: "review",
            created_at: "2026-09-19T17:00:00Z",
            file_count: 588,
            created_by: "Reviewer",
            checked_files: 588,
            failed_files: 0,
            filenames: ["Checking USD.pdf"],
          },
        ],
      } as never
    return { ...batch, id: "earlier-run" } as never
  })
  mount("/cases/case/financial?view=statements")
  expect(await screen.findByText("Latest batch")).toBeVisible()
  expect(screen.getByText(/Started by Alex/)).toBeVisible()
  expect(
    screen.getByText(/587 of 588 files checked.*1 files could not be read/)
  ).toBeVisible()
  expect(screen.getByText(/Checking USD.pdf/)).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Open batch earlier-" }))
  await waitFor(() =>
    expect(screen.getByLabelText("Location")).toHaveTextContent(
      "batch=earlier-run"
    )
  )
})

it("confirms the displayed ready list and filters problems across the batch", async () => {
  mount()
  fireEvent.click(
    await screen.findByRole("button", { name: "Import 14 transactions" })
  )
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      "/api/financial/statement-import/batches/batch/confirm?case_id=case",
      {
        method: "POST",
        body: expect.objectContaining({
          expected_ready_revision: "a".repeat(64),
          request_id: expect.any(String),
        }),
      }
    )
  )
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "Show statements with issues only",
    })
  )
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      expect.stringContaining("only_problems=true"),
      expect.objectContaining({ timeout: 60000 })
    )
  )
  expect(
    await screen.findByText(/2 prepared reviews ready.*14 transactions/)
  ).toBeVisible()
})
it("checks for additional periods without confirming another import", async () => {
  mount()
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Check for additional statement periods",
    })
  )
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      "/api/financial/statement-import/batches/batch/refresh-statements?case_id=case",
      { method: "POST" }
    )
  )
  expect(
    vi.mocked(fetchAPI).mock.calls.some(([url]) => url.includes("/confirm?"))
  ).toBe(false)
})

it("offers saving a balance-only batch without asking to import zero records", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({
    ...batch,
    available_statements: 1,
    available_records: 0,
    ready_transactions: 0,
    items: [{ ...item, transaction_count: 0, can_import: true }],
  } as never)
  mount()
  fireEvent.click(
    await screen.findByRole("button", { name: "Save 1 statement to Financial" })
  )
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      "/api/financial/statement-import/batches/batch/confirm?case_id=case",
      {
        method: "POST",
        body: expect.objectContaining({
          expected_ready_revision: "a".repeat(64),
          request_id: expect.any(String),
        }),
      }
    )
  )
})

it("shows usable payments separately from incomplete records and retained source text", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({
    ...batch,
    available_records: 250,
    available_transactions: 2,
    available_incomplete: 248,
    items: [{ ...item, unclassified_count: 400 }],
  } as never)
  mount()
  expect(
    await screen.findByRole("button", {
      name: "Import 2 transactions and 248 incomplete records",
    })
  ).toBeVisible()
  expect(screen.getByText(/400 lines of other extracted text/)).toBeVisible()
  expect(
    screen.getByText(/Incomplete records will be saved separately/)
  ).toBeVisible()
})
it("opens the exact problem row, reloads server corrections and returns after saving", async () => {
  mount()
  fireEvent.click(await screen.findByRole("button", { name: "Go to this row" }))
  await screen.findByText("Focused row: 1:0:2")
  expect(screen.getByText("Saved holder: Checked owner")).toBeVisible()
  expect(screen.getByLabelText("Location")).toHaveTextContent(
    "batchRow=1%3A0%3A2"
  )
  fireEvent.click(screen.getByRole("button", { name: "Save for bulk import" }))
  await screen.findByRole("heading", { name: "Prepare statements for import" })
  expect(fetchAPI).toHaveBeenCalledWith(
    "/api/financial/statement-import/batches/batch/items/item?case_id=case",
    {
      method: "PUT",
      body: {
        request: { checked: true },
        expected_review_revision: "b".repeat(64),
      },
    }
  )
  expect(screen.getByLabelText("Location")).not.toHaveTextContent("batchItem")
})
it("keeps a saved balance-only statement visible instead of opening an empty ledger", async () => {
  mount("/cases/case/financial?view=statements&batch=batch&batchItem=item")
  fireEvent.click(
    await screen.findByRole("button", { name: "Complete balance-only import" })
  )
  expect(screen.getByText(/Statement balances saved\./)).toBeVisible()
  expect(screen.getByLabelText("Location")).toHaveTextContent("view=statements")
  expect(screen.getByText("Saved holder: Checked owner")).toBeVisible()
})

it("refuses a response for a different case", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({
    ...batch,
    case_id: "elsewhere",
  } as never)
  mount()
  expect(await screen.findByRole("alert")).toHaveTextContent("another case")
  expect(
    screen.queryByRole("button", { name: "Import 14 transactions" })
  ).not.toBeInTheDocument()
})

it("opens the exact imported sources across the whole batch with their accounts and dates", async () => {
  const sources = Array.from({ length: 101 }, (_, n) => `source-${n}`)
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("/imported-transactions")
      ? {
          case_id: "case",
          batch_id: "batch",
          revision: "d".repeat(64),
          source_document_ids: sources,
          account_ids: ["one-account"],
          statement_count: 101,
          transaction_count: 303,
          start_date: "2020-01-01",
          end_date: "2024-12-31",
        }
      : {
          ...batch,
          counts: { imported: 101 },
          items: [{ ...item, status: "imported" }],
        }
  )
  mount()
  fireEvent.click(
    await screen.findByRole("button", { name: "Open saved results" })
  )
  await waitFor(() =>
    expect(screen.getByLabelText("Location")).toHaveTextContent(
      "view=transactions"
    )
  )
  const scope = {
    accountId: "one-account",
    startDate: "2020-01-01",
    endDate: "2024-12-31",
  }
  expect(
    Object.values(useInvestigationScopeStore.getState().scopes)
  ).toContainEqual(scope)
  expect(
    useFinancialDraftStore.getState().drafts[
      financialDraftKey("case", paymentTableDraftName(scope, true))
    ]
  ).toMatchObject({
    importBatchId: "batch",
    importBatchRevision: "d".repeat(64),
    importSourceIds: sources,
    importStatementCount: 101,
    sourceDocumentId: "",
    search: "",
  })
  expect(useFinancialStore.getState().mode).toBe("transactions")
})

it("leaves a statement unimported with a reason and restores it without removing the file", async () => {
  let skipped = false
  const choices: unknown[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/import-choice?")) {
      choices.push(options?.body)
      skipped = !skipped
      return { applied: true } as never
    }
    return {
      ...batch,
      counts: { ...batch.counts, skipped: skipped ? 1 : 0 },
      items: [
        {
          ...item,
          status: skipped ? "skipped" : "ready",
          disposition_revision: "d".repeat(64),
          import_decision: skipped
            ? { action: "skip", reason: "Duplicate copy" }
            : undefined,
        },
      ],
    } as never
  })
  mount()
  fireEvent.click(
    await screen.findByRole("button", { name: "Leave unimported" })
  )
  fireEvent.change(screen.getByLabelText("Reason to leave unimported"), {
    target: { value: "Duplicate copy" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Leave unimported" }))
  const restore = await screen.findByRole("button", {
    name: "Restore to review",
  })
  expect(screen.getByRole("heading", { name: "Checking.pdf" })).toBeVisible()
  expect(screen.getByText("Left unimported: Duplicate copy")).toBeVisible()
  fireEvent.click(restore)
  fireEvent.change(screen.getByLabelText("Reason to restore to review"), {
    target: { value: "Additional records" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Restore to review" }))
  await screen.findByRole("button", { name: "Leave unimported" })
  expect(choices).toEqual([
    {
      action: "skip",
      reason: "Duplicate copy",
      expected_revision: "d".repeat(64),
    },
    {
      action: "restore",
      reason: "Additional records",
      expected_revision: "d".repeat(64),
    },
  ])
})

it("keeps completed assignments separate from ready imports and removes the skip action", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({
    ...batch,
    counts: { ready: 0, assigned: 1 },
    ready_transactions: 0,
    items: [
      { ...item, status: "assigned", transaction_count: 0, problems: [] },
    ],
  } as never)
  mount()
  expect(
    await screen.findByText("Payments assigned", { exact: true })
  ).toBeVisible()
  expect(screen.getByText(/unassigned page review is complete/)).toBeVisible()
  expect(
    screen.getByRole("button", { name: "No statements ready to save" })
  ).toBeDisabled()
  expect(screen.queryByRole("button", { name: /Leave unimported/ })).toBeNull()
})

it("shows the actual retry decision, prevents repeat clicks and retains the receipt after reopening", async () => {
  let receipt: Record<string, unknown> | undefined = undefined
  let finish: (result: unknown) => void = () => {}
  let requests = 0
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/retry?") && options?.method === "POST") {
      requests++
      return new Promise((resolve) => {
        finish = (result) => resolve(result as never)
      })
    }
    return {
      ...batch,
      files: [
        {
          ...batch.files[0],
          status: "error",
          error: "Reading failed.",
          recovery: receipt,
        },
      ],
    } as never
  })
  const view = mount()
  const retry = await screen.findByRole("button", { name: "Retry this file" })
  fireEvent.click(retry)
  expect(
    screen.getByRole("button", { name: "Requesting retry…" })
  ).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Requesting retry…" }))
  expect(requests).toBe(1)
  receipt = {
    attempt_id: "attempt",
    action: "review_required",
    stage: "review",
    message:
      "The reading is complete. Review its balance difference; no new reading was started.",
    review_file_id: "file",
  }
  finish({ queued: false, status: "checked", ...receipt })
  await screen.findByText(/Checking.pdf: The reading is complete/)
  expect(screen.queryByText(/Retry accepted for/)).not.toBeInTheDocument()
  view.unmount()
  mount()
  await screen.findByText(String(receipt.message))
  expect(screen.getByRole("button", { name: "Open file review" })).toBeEnabled()
})

it("reports an unavailable reading status without claiming a retry was queued", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/retry?") && options?.method === "POST")
      return {
        queued: false,
        status: "processing",
        action: "check_status",
        stage: "status_unavailable",
        message:
          "The current reading job could not be verified. No duplicate job was started.",
      } as never
    return {
      ...batch,
      files: [{ ...batch.files[0], status: "processing" }],
    } as never
  })
  mount()
  fireEvent.click(await screen.findByRole("button", { name: "Check reading" }))
  await screen.findByText(
    /Checking.pdf: The current reading job could not be verified/
  )
  expect(
    screen.queryByText(/already queued or being read/)
  ).not.toBeInTheDocument()
})

const failedReadingJob = {
  id: "failed-reading-job",
  case_id: "case",
  batch_id: null,
  evidence_file_id: "retained-version",
  file_name: "Checking.pdf",
  job_type: "pdf_review",
  status: "failed",
  resumable: false,
  progress: 0,
  error_message: "Reading failed",
  file_size: 100,
  mime_type: "application/pdf",
  created_at: "2026-09-25T10:00:00Z",
  updated_at: "2026-09-25T10:00:01Z",
}

it.each(["unrelated", "ambiguous", "other-case"])(
  "does not offer a reading Retry with an %s source association",
  async (kind) => {
    vi.mocked(fetchAPI).mockImplementation(async (url) => {
      if (url.startsWith("/api/evidence/engine/jobs?"))
        return [
          {
            ...failedReadingJob,
            ...(kind === "other-case" ? { case_id: "another-case" } : {}),
          },
        ] as never
      return {
        ...batch,
        reading_job_ids: [failedReadingJob.id],
        files: [
          {
            ...batch.files[0],
            file_id:
              kind === "unrelated" ? "another-reading" : "retained-version",
          },
          ...(kind === "ambiguous"
            ? [
                {
                  ...batch.files[0],
                  source_id: "another-original",
                  file_id: "retained-version",
                },
              ]
            : []),
        ],
      } as never
    })
    mount()
    fireEvent.click(
      await screen.findByText("PDF reading jobs · pause or resume a reading")
    )
    const reading = await screen.findByRole("group", {
      name: "Financial statement reading: Checking.pdf",
    })
    expect(
      within(reading).queryByRole("button", { name: "Retry" })
    ).not.toBeInTheDocument()
    expect(
      within(reading).queryByRole("button", { name: "Clear" })
    ).not.toBeInTheDocument()
    expect(
      screen.getByText(/not linked to a current file in this batch/)
    ).toBeVisible()
    expect(
      vi.mocked(fetchAPI).mock.calls.every(([, options]) => !options?.method)
    ).toBe(true)
  }
)

it("keeps a paused batch reading Retry disabled with a visible explanation", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) => {
    if (url.startsWith("/api/evidence/engine/jobs?"))
      return [failedReadingJob] as never
    return {
      ...batch,
      status: "paused",
      reading_job_ids: [failedReadingJob.id],
      files: [{ ...batch.files[0], file_id: "retained-version" }],
    } as never
  })
  mount()
  fireEvent.click(
    await screen.findByText("PDF reading jobs · pause or resume a reading")
  )
  const reading = await screen.findByRole("group", {
    name: "Financial statement reading: Checking.pdf",
  })
  expect(within(reading).getByRole("button", { name: "Retry" })).toBeDisabled()
  expect(
    screen.getByText("Resume batch preparation before retrying a file.")
  ).toBeVisible()
})

it("shows a reading Retry error beside its control and refreshes a possibly saved receipt", async () => {
  let jobReads = 0,
    batchReads = 0
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method === "POST")
      throw Error(
        "Retry outcome could not be confirmed. Check the current reading."
      )
    if (url.startsWith("/api/evidence/engine/jobs?")) {
      jobReads++
      return [failedReadingJob] as never
    }
    batchReads++
    return {
      ...batch,
      reading_job_ids: [failedReadingJob.id],
      files: [{ ...batch.files[0], file_id: "retained-version" }],
    } as never
  })
  mount()
  const summary = await screen.findByText(
    "PDF reading jobs · pause or resume a reading"
  )
  fireEvent.click(summary)
  const reading = await screen.findByRole("group", {
    name: "Financial statement reading: Checking.pdf",
  })
  fireEvent.click(within(reading).getByRole("button", { name: "Retry" }))
  expect(
    await within(summary.closest("details")!).findByRole("alert")
  ).toHaveTextContent("Retry outcome could not be confirmed")
  await waitFor(() => {
    expect(jobReads).toBeGreaterThan(1)
    expect(batchReads).toBeGreaterThan(1)
  })
  expect(fetchAPI).toHaveBeenCalledWith(
    "/api/financial/statement-import/batches/batch/files/file/retry?case_id=case",
    { method: "POST" }
  )
  expect(
    vi
      .mocked(fetchAPI)
      .mock.calls.filter(([, options]) => options?.method === "POST")
  ).toHaveLength(1)
  expect(within(reading).getByRole("button", { name: "Retry" })).toBeEnabled()
})

it("bounds a stalled batch read, gives actionable retry, and preserves the source of the request", async () => {
  let attempts = 0
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/batches/batch?")) {
      attempts++
      expect(options?.timeout).toBe(60000)
      expect(options?.signal).toBeInstanceOf(AbortSignal)
      if (attempts === 1) throw new DOMException("Timed out", "AbortError")
      return batch
    }
    return { case_id: "case", batches: [] }
  })
  mount()
  await screen.findByText(/did not respond within one minute/)
  expect(attempts).toBe(1)
  expect(screen.getByRole("alert")).toHaveTextContent(
    "does not restart any work"
  )
  fireEvent.click(screen.getByRole("button", { name: "Retry batch" }))
  await screen.findByRole("region", { name: "Financial processing batch" })
  expect(attempts).toBe(2)
})

it("lets the investigator leave a pending batch read and aborts only that GET", async () => {
  let signal: AbortSignal | null | undefined
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/batches/batch?")) {
      signal = options?.signal
      return new Promise(() => {})
    }
    return { case_id: "case", batches: [] }
  })
  mount()
  await screen.findByRole("region", {
    name: "Opening financial processing batch",
  })
  expect(screen.getByText(/leaving this view does not stop/)).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Back to statement files" })
  )
  await waitFor(() =>
    expect(screen.getByLabelText("Location")).toHaveTextContent("files=1")
  )
  expect(signal?.aborted).toBe(true)
  expect(
    vi.mocked(fetchAPI).mock.calls.every(([, options]) => !options?.method)
  ).toBe(true)
})
