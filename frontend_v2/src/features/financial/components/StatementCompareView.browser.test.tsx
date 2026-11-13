import "@/styles/globals.css"
import "../financial-workspace.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { fetchAPI } from "@/lib/api-client"
import { importJobs } from "@/test/statement-import-jobs"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { useStatementCoverageReview } from "../hooks/use-statement-coverage-review"
import { useStatementChecks } from "../hooks/use-statement-checks"
import { StatementImportPanel } from "./StatementImportPanel"
import { BatchReviewContext } from "../lib/batch-review-context"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({
    canEdit: true,
    canUpload: true,
    ready: true,
    error: false,
  }),
}))
vi.mock("../hooks/use-statement-coverage-review", async (original) => ({
  ...(await original<
    typeof import("../hooks/use-statement-coverage-review")
  >()),
  useStatementCoverageReview: vi.fn(),
}))
vi.mock("../hooks/use-statement-checks", async (original) => ({
  ...(await original<typeof import("../hooks/use-statement-checks")>()),
  useStatementChecks: vi.fn(),
}))
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: () => <div>Synthetic original statement</div>,
}))
vi.mock("./PdfReviewIntake", () => ({ PdfReviewIntake: () => null }))
vi.mock("@/components/ui/evidence-pdf-document", () => ({
  EvidencePdfDocument: ({ evidenceId, page }: { evidenceId: string; page: number }) => (
    <p>
      {evidenceId} page {page}
    </p>
  ),
}))

const caseId = "10000000-0000-4000-8000-000000000001"
const fileId = "10000000-0000-4000-8000-000000000002"
const revision = "a".repeat(64)
const reading = {
  case_id: caseId,
  evidence_file_id: fileId,
  filename: "Synthetic January.pdf",
  currency: "USD",
  revision,
  statement_id: "b".repeat(64),
  // A combined PDF: this statement is pages 5 and 6 of 8.
  page_numbers: [1, 2, 3, 4, 5, 6, 7, 8],
  statement_page_numbers: [5, 6],
  metadata: {
    holder: "Example Ltd",
    account_number: "0012345",
    institution: "Example Bank",
    period: "January 2026",
    period_start: "2026-01-01",
    period_end: "2026-01-31",
  },
  rows: [
    {
      id: "1:0:1",
      page_number: 5,
      table_index: 0,
      row_index: 1,
      source_cells: [
        { column_index: 0, expected_text: "2026-01-02", locator: {} },
      ],
      fields: {
        date: "2026-01-02",
        description: "Original payment",
        amount_minor: "10000",
        direction: "credit",
        balance: "10000",
      },
      issues: [],
      excluded: false,
      kind: "transaction",
    },
  ],
  issues: [],
  transaction_count: 1,
  needs_attention: 0,
}
const ignored = {
  policy: "pending-statement-duplicate-v1",
  reading_revision: revision,
  revision: "c".repeat(64),
  status: "ignored",
  current: true,
  label: "Duplicate - Ignored by system",
  reason: "The original and financial reading match.",
  matched_fields: [
    "bank",
    "full_account_number",
    "account_holder",
    "period_start",
    "period_end",
  ],
  basis: "identical_financial_reading",
  retained: {
    evidence_file_id: "10000000-0000-4000-8000-000000000003",
    filename: "Retained January.pdf",
    page_number: 1,
  },
}
let duplicateResponse: Promise<unknown>
let returnDecision = false
let client: QueryClient

beforeEach(async () => {
  await page.viewport(1440, 1000)
  sessionStorage.clear()
  useAuthStore.setState({
    user: { id: "reviewer", username: "reviewer" } as never,
  })
  useStatementWorkspace.setState({
    selections: { [`reviewer:${caseId}`]: { fileId, open: true } },
    reviewChoices: {},
    pages: {},
    sectionSearches: {},
  })
  vi.mocked(useStatementCoverageReview).mockReturnValue({
    data: { available: true, candidates: [], revision: "d".repeat(64) },
    pending: false,
    error: undefined,
    retry: vi.fn(),
  })
  vi.mocked(useStatementChecks).mockReturnValue({
    checks: [],
    admission: {
      can_import: true,
      status: "reconciled",
      revision: "e".repeat(64),
      blockers: [],
    },
    pending: false,
    error: undefined,
    revision: "e".repeat(64),
    retry: vi.fn(),
  })
  returnDecision = false
  duplicateResponse = Promise.resolve({
    case_id: caseId,
    evidence_file_id: fileId,
    statement_id: reading.statement_id,
    duplicate_disposition: ignored,
  })
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(importJobs(async (url) => {
    if (url.startsWith("/api/evidence-upload-")) return [] as never
    if (/^\/api\/evidence(\/statement-register)?\?/.test(url))
      return {
        files: [
          {
            id: fileId,
            case_id: caseId,
            original_filename: reading.filename,
            status: "processed",
          },
        ],
      } as never
    if (url.includes("/compare-facts?")) return facts as never
    if (url.includes("/duplicate-disposition?"))
      return (await duplicateResponse) as never
    if (url.includes("/confirm?"))
      return {
        case_id: caseId,
        evidence_file_id: fileId,
        outcome: "duplicate_ignored",
        ignored: true,
        applied: true,
        created: false,
        transaction_count: 0,
        record_count: 0,
        incomplete_count: 0,
        source_document_id: null,
        account_id: null,
        issues: [],
        duplicate_disposition: ignored,
      } as never
    return {
      ...reading,
      ...(returnDecision
        ? {
            duplicate_disposition: {
              ...ignored,
              status: "not_duplicate",
              label: "No confirmed duplicate",
            },
          }
        : {}),
    } as never
  }))
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
})
afterEach(() => {
  cleanup()
  client.clear()
  vi.clearAllMocks()
})

async function mount() {
  const onImported = vi.fn()
  render(
    <QueryClientProvider client={client}>
      <StatementImportPanel caseId={caseId} onImported={onImported} />
    </QueryClientProvider>
  )
  await screen.findByText(`Review ${reading.filename}`)
  fireEvent.click(
    screen.getByRole("button", { name: "Show corrections and import choices" })
  )
  return onImported
}

const originalId = "10000000-0000-4000-8000-000000000003"
const facts = {
  case_id: caseId,
  source_document_id: "10000000-0000-4000-8000-000000000009",
  evidence_file_id: originalId,
  filename: "Retained January.pdf",
  institution: "Example Bank",
  account_number: "0012345",
  holder: "Example Ltd",
  period_start: "2026-01-01",
  period_end: "2026-01-31",
  currency: "USD",
  balance_convention: "asset_balance",
  pages: [1, 2],
  opening_balance_minor: null,
  closing_balance_minor: null,
  payment_count: 1,
  money_in_minor: "10000",
  money_out_minor: "0",
  held_from_ledger: 0,
  mixed_currency: false,
}
const candidate = {
  file_id: originalId,
  source_document_id: facts.source_document_id,
  filename: "Retained January.pdf",
  page_number: 1,
  status: "imported" as const,
  period_start: "2026-01-01",
  period_end: "2026-01-31",
  matching_statement: true,
}
const needsComparison = {
  ...ignored,
  status: "needs_comparison",
  basis: "investigator_decision",
  label: "Compare this statement",
  reason: "Another imported statement has the same account and dates.",
}
const leftOut = { ...needsComparison, revision: "9".repeat(64), status: "ignored", label: "Left unimported" }

function holdAsPossibleDuplicate() {
  vi.mocked(useStatementCoverageReview).mockReturnValue({
    data: {
      available: true,
      candidates: [candidate],
      matching_statement: true,
      revision: "d".repeat(64),
    },
    pending: false,
    error: undefined,
    retry: vi.fn(),
  })
  duplicateResponse = Promise.resolve({
    case_id: caseId,
    evidence_file_id: fileId,
    statement_id: reading.statement_id,
    duplicate_disposition: needsComparison,
  })
}

async function openCompare() {
  holdAsPossibleDuplicate()
  await mount()
  fireEvent.click(await screen.findByRole("button", { name: "Compare side by side" }))
  return screen.findByRole("dialog", { name: "Compare side by side" })
}

it("opens both statements side by side from their own first pages with the facts compared", async () => {
  const dialog = await openCompare()
  const mine = within(dialog).getByRole("region", { name: "This statement" })
  const theirs = within(dialog).getByRole("region", { name: "Matching statement" })
  expect(within(mine).getByText(`${fileId} page 5`)).toBeVisible()
  expect(within(mine).getByText(/Pages 5 to 6 · Held as possible duplicate/)).toBeVisible()
  expect(within(theirs).getByText(`${originalId} page 1`)).toBeVisible()
  expect(await within(theirs).findByText(/Pages 1 to 2 · Already imported/)).toBeVisible()
  const strip = within(dialog).getByRole("region", { name: "Compared facts" })
  expect(await within(strip).findByRole("row", { name: /^Money in 100\.00 USD 100\.00 USD Agrees/ })).toBeVisible()
  expect(within(strip).getByRole("row", { name: /^Number of payments 1 1 Agrees/ })).toBeVisible()
})

it("decides from inside the view: the statement screen and the review queue follow, and the view stays open", async () => {
  const invalidate = vi.spyOn(client, "invalidateQueries")
  const dialog = await openCompare()
  const area = within(dialog).getByRole("region", { name: "Decision in the comparison" })
  duplicateResponse = Promise.resolve({
    case_id: caseId,
    evidence_file_id: fileId,
    statement_id: reading.statement_id,
    duplicate_disposition: leftOut,
  })
  fireEvent.click(await within(area).findByRole("button", { name: "Don’t import this duplicate" }))
  expect(await within(area).findByRole("heading", { name: "Duplicate — left unimported" })).toBeVisible()
  expect(screen.getByRole("dialog", { name: "Compare side by side" })).toBeVisible()
  expect(within(dialog).getByRole("region", { name: "This statement" })).toHaveTextContent("Left unimported")
  await waitFor(() =>
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["financial-review-queue", caseId] })
  )
  fireEvent.click(within(dialog).getByRole("button", { name: "Close comparison" }))
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
  expect(
    screen.getAllByRole("heading", { name: "Duplicate — left unimported" })[0]
  ).toBeVisible()
})

it("stacks the documents with a switch on a 390 wide screen and never scrolls the page sideways", async () => {
  await page.viewport(390, 844)
  const dialog = await openCompare()
  const mine = within(dialog).getByRole("region", { name: "This statement" })
  const theirs = dialog.querySelector<HTMLElement>('section[aria-label="Matching statement"]')!
  expect(mine).toBeVisible()
  expect(theirs).not.toBeVisible()
  fireEvent.click(within(dialog).getByRole("button", { name: "Matching statement" }))
  expect(theirs).toBeVisible()
  expect(mine).not.toBeVisible()
  await within(dialog).findByRole("row", { name: /^Money in/ })
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(390)
  expect((dialog as HTMLElement).scrollWidth).toBeLessThanOrEqual((dialog as HTMLElement).clientWidth)
})

it("shows both documents together on a wide screen", async () => {
  const dialog = await openCompare()
  expect(within(dialog).getByRole("region", { name: "This statement" })).toBeVisible()
  expect(within(dialog).getByRole("region", { name: "Matching statement" })).toBeVisible()
  expect(dialog.querySelector('[aria-label="Choose a document"]')).not.toBeVisible()
})

it("opens one comparison from the queue's Compare, not a second one from the register behind it", async () => {
  holdAsPossibleDuplicate()
  const before = window.location.href
  window.history.replaceState(null, "", "?view=statements&queue=1&queueItem=q1&queueCompare=q1")
  try {
    render(
      <QueryClientProvider client={client}>
        <StatementImportPanel caseId={caseId} onImported={vi.fn()} />
        <BatchReviewContext.Provider value={{ save: vi.fn(), saved: vi.fn() }}>
          <StatementImportPanel caseId={caseId} onImported={vi.fn()} />
        </BatchReviewContext.Provider>
      </QueryClientProvider>
    )
    expect(await screen.findByRole("dialog", { name: "Compare side by side" })).toBeVisible()
    await new Promise((resolve) => setTimeout(resolve, 500))
    expect(screen.getAllByRole("dialog", { name: "Compare side by side" })).toHaveLength(1)
  } finally {
    window.history.replaceState(null, "", before)
  }
})
