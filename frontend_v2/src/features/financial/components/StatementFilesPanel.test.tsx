vi.mock("./StatementRecoveryPanel", () => ({
  StatementRecoveryPanel: () => null,
}))
// This existing workflow fixture has case editing and upload access.
vi.mock("../hooks/use-financial-access", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../hooks/use-financial-access")>()),
  useFinancialAccess: () => ({
    canEdit: true,
    canUpload: true,
    ready: true,
    error: false,
  }),
}))
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { MemoryRouter, useLocation } from "react-router-dom"
import { StatementFilesPanel } from "./StatementFilesPanel"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { fetchAPI } from "@/lib/api-client"
import { evidenceAPI } from "@/features/evidence/api"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
// Upload interruption is exercised with the real panel in Chromium.
vi.mock("@/features/evidence/components/ResumableUploadsPanel", () => ({
  ResumableUploadsPanel: () => null,
}))
vi.mock("@/features/evidence/api", () => ({
  evidenceAPI: { preparePdfReview: vi.fn() },
}))
const file = {
  id: "file",
  case_id: "case",
  original_filename: "statement.pdf",
  status: "failed",
}
const status = { case_id: "case", files: [], truncated: false }
function responses(files = [file], saved = status) {
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("/statement-import/files") ? saved : { files }
  )
}
function Location() {
  const location = useLocation()
  return (
    <output aria-label="Location">
      {location.pathname}
      {location.search}
    </output>
  )
}
function mount(register = false) {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <StatementFilesPanel caseId="case" register={register} />
        <Location />
      </MemoryRouter>
    </QueryClientProvider>
  )
}
beforeEach(() => {
  vi.resetAllMocks()
  useStatementWorkspace.setState({ selections: {}, reviewChoices: {} })
  responses()
})

const duplicateDecision = {
  policy: "pending-statement-duplicate-v1",
  reading_revision: "a".repeat(64),
  revision: "b".repeat(64),
  current: true,
  status: "ignored",
  label: "Duplicate - Ignored by system",
  reason:
    "The contents match the retained statement. Evidence and edits remain available.",
  matched_fields: ["bank", "full_account_number", "account_holder"],
  basis: "identical_financial_reading",
  retained: {
    evidence_file_id: "10000000-0000-4000-8000-000000000003",
    filename: "Retained synthetic source.pdf",
    page_number: 1,
  },
}

it("shows an ignored file, exposes its retained source and opens its exact period for comparison", async () => {
  const period = "c".repeat(64)
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("/statement-import/files")
      ? {
          case_id: "case",
          truncated: false,
          files: [
            {
              evidence_file_id: "file",
              current_transactions: 0,
              periods: [],
              prepared_periods: 1,
              ignored_periods: 1,
              available_periods: 0,
              periods_with_checks: 0,
              duplicate_dispositions: [
                {
                  statement_id: period,
                  currency: "USD",
                  decision: duplicateDecision,
                },
              ],
            },
          ],
        }
      : { files: [{ ...file, status: "processed" }] }
  )
  mount(true)
  const choice = await screen.findByLabelText("Show files")
  expect(choice).toHaveValue("action")
  expect(
    screen.queryByRole("button", { name: "Review duplicate decision" })
  ).not.toBeInTheDocument()
  fireEvent.change(choice, { target: { value: "duplicates" } })
  expect(
    screen.getByText("Duplicate decisions · evidence retained")
  ).toBeVisible()
  expect(
    screen.getAllByText("Duplicate - Ignored by system").length
  ).toBeGreaterThan(0)
  expect(
    screen.getByRole("button", {
      name: "Show 0 statements ready to save",
    })
  ).toBeVisible()
  fireEvent.click(screen.getByText("Duplicate decisions · evidence retained"))
  expect(
    screen.getByText("Retained source: Retained synthetic source.pdf")
  ).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Review duplicate decision" })
  )
  expect(
    Object.values(useStatementWorkspace.getState().reviewChoices)
  ).toContainEqual({ statementId: period, currency: "" })
  expect(
    vi
      .mocked(fetchAPI)
      .mock.calls.every(
        ([, options]) => !options?.method || options.method === "GET"
      )
  ).toBe(true)
})

it("keeps a different period in a mixed file ready while showing its ignored copy separately", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("/statement-import/files")
      ? {
          case_id: "case",
          truncated: false,
          files: [
            {
              evidence_file_id: "file",
              current_transactions: 0,
              periods: [],
              prepared_periods: 2,
              ignored_periods: 1,
              available_periods: 1,
              periods_with_checks: 0,
              duplicate_dispositions: [
                {
                  statement_id: "c".repeat(64),
                  currency: "USD",
                  decision: duplicateDecision,
                },
              ],
              ready_periods: [
                {
                  statement_id: "separate-ready-period",
                  holder: "Synthetic holder",
                  institution: "Synthetic Bank",
                  account: "TEST-2",
                  currency: "USD",
                  period_start: "2026-02-01",
                  period_end: "2026-02-28",
                  transaction_count: 2,
                  incomplete_count: 0,
                  problem_count: 0,
                },
              ],
            },
          ],
        }
      : { files: [{ ...file, status: "processed" }] }
  )
  mount(true)
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Show 1 statement ready to save",
    })
  )
  expect(screen.getByText(/1 duplicate period ignored/)).toBeVisible()
  expect(screen.getByText("2026-02-01 to 2026-02-28")).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Review and import" }))
  expect(
    Object.values(useStatementWorkspace.getState().reviewChoices)
  ).toContainEqual({ statementId: "separate-ready-period", currency: "" })
})

it("does not carry an ignored decision from an older reading onto its current replacement", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("/statement-import/files")
      ? {
          case_id: "case",
          truncated: false,
          files: [
            {
              evidence_file_id: "file",
              current_transactions: 0,
              periods: [],
              prepared_periods: 1,
              ignored_periods: 1,
              duplicate_dispositions: [
                {
                  statement_id: null,
                  currency: "USD",
                  decision: duplicateDecision,
                },
              ],
            },
            {
              evidence_file_id: "new-reading",
              current_transactions: 0,
              periods: [],
              prepared_periods: 1,
              ignored_periods: 0,
              periods_with_checks: 1,
              duplicate_dispositions: [
                {
                  statement_id: null,
                  currency: "USD",
                  decision: {
                    ...duplicateDecision,
                    current: false,
                    status: "needs_comparison",
                    label: "Compare this statement",
                    reason:
                      "The reading changed. Check these statements again.",
                  },
                },
              ],
            },
          ],
        }
      : {
          files: [
            { ...file, status: "processed", created_at: "2026-01-01" },
            {
              ...file,
              id: "new-reading",
              status: "processed",
              statement_root_evidence_id: "file",
              statement_parent_evidence_id: "file",
              created_at: "2026-01-02",
            },
          ],
        }
  )
  mount(true)
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Show 1 files with checks to review",
    })
  )
  expect(
    screen.queryByText("Duplicate - Ignored by system")
  ).not.toBeInTheDocument()
  fireEvent.click(screen.getByText("Duplicate decisions · evidence retained"))
  expect(screen.getByText("Compare this statement")).toBeVisible()
})
it("reveals ready periods, clears stale search and opens the exact period without importing", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("/statement-import/files")
      ? {
          case_id: "case",
          truncated: false,
          files: [
            {
              evidence_file_id: "file",
              current_transactions: 0,
              periods: [],
              prepared_periods: 2,
              available_periods: 1,
              ready_periods: [
                {
                  statement_id: "ready-second-period",
                  holder: "Synthetic holder",
                  institution: "Example Bank",
                  account: "TEST-2",
                  currency: "USD",
                  period_start: "2024-02-01",
                  period_end: "2024-02-29",
                  transaction_count: 3,
                  incomplete_count: 0,
                  problem_count: 1,
                },
              ],
            },
          ],
        }
      : { files: [{ ...file, status: "processed" }] }
  )
  mount(true)
  const ready = await screen.findByRole("button", {
    name: "Show 1 statement ready to save",
  })
  fireEvent.change(screen.getByLabelText("Search statement files"), {
    target: { value: "no matching filename" },
  })
  fireEvent.click(ready)
  expect(screen.getByLabelText("Search statement files")).toHaveValue("")
  expect(ready).toHaveAttribute("aria-pressed", "true")
  expect(screen.getByText("2024-02-01 to 2024-02-29")).toBeVisible()
  expect(screen.getByText(/3 payments ready to import/)).toHaveTextContent(
    "1 check to review"
  )
  const heading = screen.getByRole("heading", {
    name: "Ready to import · 1 statement period in 1 file",
  })
  await waitFor(() => expect(heading).toHaveFocus())
  fireEvent.click(ready)
  await waitFor(() => expect(heading).toHaveFocus())
  fireEvent.click(screen.getByRole("button", { name: "Review and import" }))
  expect(
    Object.values(useStatementWorkspace.getState().reviewChoices)
  ).toContainEqual({ statementId: "ready-second-period", currency: "" })
  expect(
    Object.values(useStatementWorkspace.getState().selections)
  ).toContainEqual({ fileId: "file", open: true })
  expect(
    vi
      .mocked(fetchAPI)
      .mock.calls.every(
        ([, options]) => !options?.method || options.method === "GET"
      )
  ).toBe(true)
})

it("keeps the review action available while an older server has only readiness counts", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("/statement-import/files")
      ? {
          case_id: "case",
          truncated: false,
          files: [
            {
              evidence_file_id: "file",
              current_transactions: 0,
              periods: [],
              available_periods: 1,
            },
          ],
        }
      : { files: [{ ...file, status: "processed" }] }
  )
  mount(true)
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Show 1 statement ready to save",
    })
  )
  fireEvent.click(screen.getByRole("button", { name: "Review and import" }))
  expect(
    Object.values(useStatementWorkspace.getState().selections)
  ).toContainEqual({ fileId: "file", open: true })
})
it("prepares all selected files directly, keeps hidden selections and reuses a failed request", async () => {
  const files = Array.from({ length: 3 }, (_, n) => ({
    ...file,
    id: `file-${n}`,
    original_filename: `Statements ${n}.pdf`,
    status: "processed",
  }))
  const attempts: unknown[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method === "POST") {
      attempts.push(options.body)
      if (attempts.length === 1) throw Error("Connection lost")
      return { id: "new-batch", case_id: "case" } as never
    }
    return (
      url.includes("/statement-import/files") ? status : { files }
    ) as never
  })
  mount(true)
  fireEvent.click(
    await screen.findByRole("button", { name: "Select all 3 shown files" })
  )
  fireEvent.change(screen.getByLabelText("Search statement files"), {
    target: { value: "Statements 1" },
  })
  expect(
    screen.getByText("3 files selected · 2 hidden by filters")
  ).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Review and save selected files together (3)",
    })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Your selection is kept"
  )
  expect(screen.getByLabelText("Select Statements 1.pdf")).toBeChecked()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Review and save selected files together (3)",
    })
  )
  await waitFor(() =>
    expect(screen.getByLabelText("Location")).toHaveTextContent(
      "/cases/case/financial?view=statements&batch=new-batch"
    )
  )
  expect(attempts).toHaveLength(2)
  expect(attempts[0]).toEqual(attempts[1])
  expect(attempts[1]).toMatchObject({
    file_ids: ["file-0", "file-1", "file-2"],
    folder_ids: [],
  })
  expect(fetchAPI).not.toHaveBeenCalledWith(
    expect.stringContaining("/confirm"),
    expect.anything()
  )
})

it("does not navigate to a batch belonging to a different case", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method === "POST")
      return { id: "wrong-batch", case_id: "other" } as never
    return (
      url.includes("/statement-import/files")
        ? status
        : { files: [{ ...file, status: "processed" }] }
    ) as never
  })
  mount(true)
  fireEvent.click(
    await screen.findByRole("button", { name: "Select all 1 shown file" })
  )
  fireEvent.click(
    screen.getByRole("button", {
      name: "Review and save selected files together (1)",
    })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent("another case")
  expect(screen.getByLabelText("Location")).not.toHaveTextContent("wrong-batch")
})
it("reads the existing failed file without uploading another copy", async () => {
  vi.mocked(evidenceAPI.preparePdfReview).mockImplementation(async () => {
    responses([{ ...file, status: "processed" }])
    return { job_ids: ["job"] }
  })
  mount()
  fireEvent.click(
    await screen.findByRole("button", { name: "Retry reading: statement.pdf" })
  )
  await waitFor(() =>
    expect(evidenceAPI.preparePdfReview).toHaveBeenCalledWith("case", "file")
  )
  expect(
    await screen.findByRole("button", {
      name: /statement.pdf.*PDF read.*open review to check and import/,
    })
  ).toBeEnabled()
  expect(
    vi
      .mocked(fetchAPI)
      .mock.calls.every(([url]) =>
        [
          "/api/evidence?case_id=case&include_reading_versions=true&financial_only=true",
          "/api/financial/statement-import/files?case_id=case",
        ].includes(url)
      )
  ).toBe(true)
})
it("retains the file and reports an uncertain failed request without automatically retrying", async () => {
  vi.mocked(evidenceAPI.preparePdfReview).mockRejectedValue(
    Error("Connection lost.")
  )
  mount()
  fireEvent.click(
    await screen.findByRole("button", { name: "Retry reading: statement.pdf" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Your uploaded PDF is retained"
  )
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Retry reading: statement.pdf" })
    ).toBeEnabled()
  )
  expect(evidenceAPI.preparePdfReview).toHaveBeenCalledTimes(1)
})
it("offers reading for an unprocessed file but never for an active job", async () => {
  responses([
    { ...file, status: "unprocessed" },
    {
      ...file,
      id: "active",
      original_filename: "active.pdf",
      status: "processing",
    },
  ])
  mount()
  expect(
    await screen.findByRole("button", { name: "Read statement: statement.pdf" })
  ).toBeEnabled()
  expect(
    screen.queryByRole("button", { name: /reading: active.pdf/i })
  ).not.toBeInTheDocument()
  expect(
    screen.getByRole("button", { name: /active.pdf.*processing/ })
  ).toBeDisabled()
})
it("shows saved import counts and periods after reopening the file list", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("/statement-import/files")
      ? {
          case_id: "case",
          truncated: false,
          files: [
            {
              evidence_file_id: "file",
              current_transactions: 12,
              periods: [
                {
                  id: "period",
                  account_id: "account",
                  account_label: "Business account",
                  start: "2023-01-01",
                  end: "2023-12-31",
                  source_status: "admitted",
                },
              ],
            },
          ],
        }
      : { files: [{ ...file, status: "processed" }] }
  )
  mount()
  expect(
    await screen.findByText("12 imported payments · 1 recorded period")
  ).toBeInTheDocument()
  expect(
    screen.getByText(/Business account · 2023-01-01 to 2023-12-31/)
  ).toBeInTheDocument()
  expect(screen.queryByText("Ready to review")).not.toBeInTheDocument()
})

it("shows a saved wire review as a finding and provides a link without suggesting a payment import", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("/statement-import/files")
      ? {
          case_id: "case",
          truncated: false,
          files: [
            {
              evidence_file_id: "file",
              current_transactions: 0,
              periods: [],
              wire_review_count: 1,
            },
          ],
        }
      : {
          files: [
            { ...file, original_filename: "wire.pdf", status: "processed" },
          ],
        }
  )
  mount()
  expect(
    await screen.findByRole("button", { name: /wire.pdf.*1 saved wire review/ })
  ).toBeEnabled()
  expect(
    screen.getByRole("link", { name: "Open saved wire reviews in Findings" })
  ).toHaveAttribute("href", "/cases/case/financial?view=findings")
  expect(screen.queryByText(/0 imported payments/)).toBeNull()
})

it("keeps a balance-only statement in the imported file filter", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("/statement-import/files")
      ? {
          case_id: "case",
          truncated: false,
          files: [
            {
              evidence_file_id: "file",
              current_transactions: 0,
              periods: [
                {
                  id: "period",
                  account_id: "account",
                  account_label: "BBVA example",
                  start: "2021-01-01",
                  end: "2021-01-31",
                  source_status: "admitted",
                },
              ],
            },
          ],
        }
      : { files: [{ ...file, status: "processed" }] }
  )
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <StatementFilesPanel caseId="case" register />
      </MemoryRouter>
    </QueryClientProvider>
  )
  // A saved statement needs nothing, so the default Needs action view omits it.
  expect(
    await screen.findByRole("button", { name: "Needs action (0)" })
  ).toBeVisible()
  expect(
    screen.queryByText("Statement saved · 1 recorded period · no payments")
  ).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText("Show files"), {
    target: { value: "imported" },
  })
  expect(
    screen.getByText("Statement saved · 1 recorded period · no payments")
  ).toBeVisible()
  fireEvent.change(screen.getByLabelText("Show files"), {
    target: { value: "review" },
  })
  expect(
    screen.queryByText("Statement saved · 1 recorded period · no payments")
  ).not.toBeInTheDocument()
})

it("shows non-PDF financial sources with their original and keeps them out of PDF bulk controls", async () => {
  responses([
    file,
    ...[
      "payments.csv",
      "invoice.docx",
      "accounts.xlsx",
      "receipt.png",
      "legacy.xls",
    ].map((name) => ({
      ...file,
      id: name,
      original_filename: name,
      status: "unprocessed",
    })),
  ])
  mount(true)
  const source = await screen.findByRole("article", {
    name: "Financial source payments.csv",
  })
  expect(source).toHaveTextContent(
    "Adding this source to Financial does not import transactions"
  )
  expect(
    screen.getByRole("article", { name: "Financial source legacy.xls" })
  ).toHaveTextContent("converted to XLSX or CSV")
  expect(
    screen.getAllByRole("link", { name: "Open source in Evidence" })[0]
  ).toHaveAttribute(
    "href",
    "/cases/case/evidence?file=payments.csv&from=financial"
  )
  expect(screen.queryByLabelText("Select payments.csv")).not.toBeInTheDocument()
  fireEvent.click(
    screen.getByRole("button", { name: "Select all 1 shown file" })
  )
  expect(
    screen.getByRole("button", {
      name: "Review and save selected files together (1)",
    })
  ).toBeEnabled()
  expect(screen.getByText("1 file selected")).toBeVisible()
  expect(evidenceAPI.preparePdfReview).not.toHaveBeenCalled()
})

it("offers a clear review action and batch review for read files without a prepared status", async () => {
  responses([{ ...file, status: "processed" }])
  vi.mocked(fetchAPI).mockImplementation(async (url) => {
    if (url.includes("/statement-import/batches"))
      return { id: "batch", case_id: "case" }
    if (url.includes("/statement-import/files")) return status
    return { files: [{ ...file, status: "processed" }] }
  })
  mount(true)
  expect(
    await screen.findByRole("button", { name: "Review and import" })
  ).toBeVisible()
  expect(screen.getByText(/not included in the ready counts/)).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Start batch check of 1 read file" })
  )
  await waitFor(() =>
    expect(screen.getByLabelText("Location")).toHaveTextContent("batch=batch")
  )
  expect(fetchAPI).toHaveBeenCalledWith(
    expect.stringContaining("/statement-import/batches"),
    expect.objectContaining({
      body: expect.objectContaining({ file_ids: ["file"] }),
    })
  )
})

it("identifies a saved copy without counting its payments a second time", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("/statement-import/files")
      ? {
          ...status,
          files: [
            {
              evidence_file_id: "file",
              same_pdf_saved_file_ids: ["earlier"],
              current_transactions: 0,
              periods: [],
            },
          ],
        }
      : { files: [{ ...file, status: "processed" }] }
  )
  mount(true)
  expect(
    await screen.findByText("Same PDF has saved records · review this copy")
  ).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Review reading and saved records" })
  )
  expect(
    Object.values(useStatementWorkspace.getState().selections)
  ).toContainEqual({ fileId: "file", open: true })
})

it("names the period of incomplete records and opens them from the card without nesting buttons", async () => {
  const period = (id: string, start: string, end: string) => ({
    id,
    account_id: "account",
    account_label: "Card account",
    start,
    end,
    source_status: "admitted",
  })
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("/statement-import/files")
      ? {
          case_id: "case",
          truncated: false,
          files: [
            {
              evidence_file_id: "file",
              current_transactions: 300,
              incomplete_count: 3,
              awaiting_reconciliation_count: 2,
              incomplete_sources: [
                {
                  source_document_id: "source",
                  period_start: "2020-10-08",
                  period_end: "2020-11-09",
                  missing_count: 1,
                  awaiting_reconciliation_count: 2,
                  blockers: [
                    "The payments do not add up to the printed closing balance.",
                  ],
                },
              ],
              prepared_periods: 3,
              repeat_periods: 1,
              overlapping_periods: 2,
              periods_with_checks: 0,
              periods: [
                period("one", "2020-10-08", "2020-11-09"),
                period("two", "2020-11-10", "2020-12-09"),
              ],
            },
          ],
        }
      : url.includes("/incomplete-records?")
        ? { records: [], total: 0, statements: [] }
        : { files: [{ ...file, status: "processed" }] }
  )
  mount()
  expect(
    await screen.findByText(
      "300 usable transactions · 1 incomplete record to check · 2 completed records waiting for the statement to reconcile"
    )
  ).toBeInTheDocument()
  expect(
    screen.getByText(
      /2 of 2 statement periods saved · 1 repeat reading of an already saved period, not imported again · 2 periods overlap another supplied statement/
    )
  ).toBeInTheDocument()
  expect(screen.queryByText(/checks to review/)).toBeNull()
  expect(
    screen.getByText(/Period 2020-10-08 to 2020-11-09: 1 incomplete record to check/)
  ).toHaveTextContent(
    "Still needed before they enter Transactions: The payments do not add up to the printed closing balance."
  )
  const show = screen.getByRole("button", {
    name: "Show 3 records to check in statement.pdf",
  })
  expect(show.closest("button")?.parentElement?.closest("button")).toBeNull()
  fireEvent.click(show)
  expect(show).toHaveAttribute("aria-expanded", "true")
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      expect.stringMatching(/incomplete-records\?.*evidence_file_id=file/)
    )
  )
})

it("opens on Needs action, counts not-imported cards exactly and filters without starting any work", async () => {
  const empty = (reason: string, message: string) => ({
    reason,
    message,
  })
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("/statement-import/files")
      ? {
          case_id: "case",
          truncated: false,
          files: [
            {
              evidence_file_id: "scan",
              current_transactions: 0,
              periods: [],
              prepared_periods: 1,
              empty_reading: empty(
                "scanned_image",
                "Nothing could be read: scanned image, needs visual reading"
              ),
            },
            {
              evidence_file_id: "layout",
              current_transactions: 0,
              periods: [],
              prepared_periods: 1,
              empty_reading: empty(
                "layout_not_supported",
                "Nothing could be read: layout not supported yet"
              ),
            },
            {
              evidence_file_id: "saved",
              current_transactions: 5,
              periods: [
                {
                  id: "p",
                  account_id: "a",
                  account_label: "Saved account",
                  start: "2024-01-01",
                  end: "2024-01-31",
                  source_status: "admitted",
                },
              ],
            },
          ],
        }
      : {
          files: ["scan", "layout", "saved", "unsaved"].map((id) => ({
            ...file,
            id,
            original_filename: `${id}.pdf`,
            status: "processed",
          })),
        }
  )
  mount(true)
  expect(await screen.findByLabelText("Show files")).toHaveValue("action")
  const filters = await screen.findByRole("group", { name: "Filter the list" })
  expect(
    await screen.findByRole("button", { name: "Not imported (3)" })
  ).toBeVisible()
  expect(screen.getByText(/Not imported: 3/)).toBeVisible()
  expect(
    screen.getByText(
      "Not imported · Nothing could be read: scanned image, needs visual reading"
    )
  ).toBeVisible()
  expect(
    screen.getByText(
      "Not imported · Nothing could be read: layout not supported yet"
    )
  ).toBeVisible()
  expect(screen.queryByText("saved.pdf")).not.toBeInTheDocument()
  // The batch check starts work, so it is not among the filters.
  expect(
    filters.querySelector("button")?.textContent?.includes("batch check")
  ).toBe(false)
  expect(
    screen.getByRole("region", { name: "Batch check" })
  ).toHaveTextContent("This starts work")
  expect(filters).toHaveTextContent("Show 0 imports in progress")
  const before = vi.mocked(fetchAPI).mock.calls.length
  for (const name of [
    "Not imported (3)",
    "Show all files",
    "Show 0 imports in progress",
    "Review duplicates",
    "Needs action (3)",
  ])
    fireEvent.click(screen.getByRole("button", { name }))
  expect(vi.mocked(fetchAPI).mock.calls.length).toBe(before)
  fireEvent.click(screen.getByRole("button", { name: "Not imported (3)" }))
  expect(
    document.querySelectorAll('[data-not-imported="true"]').length
  ).toBe(3)
  fireEvent.click(screen.getByRole("button", { name: "Show all files" }))
  expect(screen.getByText("saved.pdf")).toBeVisible()
  expect(
    document.querySelectorAll('[data-not-imported="true"]').length
  ).toBe(3)
})

it("offers Edit account details for the shown files without ticking, including empty readings", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/account-details/statements"))
      return { case_id: "case", items: [], notices: [] } as never
    if (url.includes("/statement-import/files"))
      return {
        case_id: "case",
        truncated: false,
        files: [
          {
            evidence_file_id: "empty",
            current_transactions: 0,
            periods: [],
            prepared_periods: 1,
            empty_reading: {
              reason: "layout_not_supported",
              message: "Nothing could be read: layout not supported yet",
            },
          },
        ],
      } as never
    void options
    return {
      files: ["empty", "other"].map((id) => ({
        ...file,
        id,
        original_filename: `${id}.pdf`,
        status: "processed",
      })),
    } as never
  })
  mount(true)
  const edit = await screen.findByRole("button", {
    name: "Edit account details of 2 shown files",
  })
  expect(edit).toBeEnabled()
  expect(
    screen.getByText(/With nothing ticked, Edit account details covers the files shown/)
  ).toBeVisible()
  fireEvent.click(edit)
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      expect.stringContaining("/account-details/statements"),
      expect.objectContaining({
        body: { file_ids: ["empty", "other"] },
      })
    )
  )
  fireEvent.click(screen.getByLabelText("Select empty.pdf"))
  expect(
    screen.getByRole("button", { name: "Edit account details" })
  ).toBeEnabled()
})
