import { fireEvent, render, screen, waitFor } from "@testing-library/react"
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
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
vi.mock("./StatementImportPanel", () => ({
  StatementImportPanel: () => {
    const ctx = useBatchReview()
    return (
      <>
        <p>Focused row: {ctx?.rowId}</p>
        <p>Saved holder: {ctx?.draft?.holder}</p>
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
      { method: "POST", body: { expected_ready_revision: "a".repeat(64) } }
    )
  )
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "Show statements with issues only",
    })
  )
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      expect.stringContaining("only_problems=true")
    )
  )
  expect(
    await screen.findByText(/2 statements available.*14 transactions/)
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
    await screen.findByRole("button", { name: "Save 1 statement" })
  )
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      "/api/financial/statement-import/batches/batch/confirm?case_id=case",
      { method: "POST", body: { expected_ready_revision: "a".repeat(64) } }
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
    await screen.findByRole("button", { name: "Open imported transactions" })
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
    screen.getByRole("button", { name: "Import 0 transactions" })
  ).toBeDisabled()
  expect(screen.queryByRole("button", { name: /Leave unimported/ })).toBeNull()
})
