import "@/styles/globals.css"
import "../financial-workspace.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { fetchAPI } from "@/lib/api-client"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { useStatementCoverageReview } from "../hooks/use-statement-coverage-review"
import { useStatementChecks } from "../hooks/use-statement-checks"
import { StatementImportPanel } from "./StatementImportPanel"

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
  page_numbers: [1, 2],
  statement_page_numbers: [1, 2],
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
      page_number: 1,
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
  vi.mocked(fetchAPI).mockImplementation(async (url) => {
    if (url.startsWith("/api/evidence-upload-")) return [] as never
    if (url.startsWith("/api/evidence?"))
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
  })
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
function editDescription() {
  fireEvent.change(screen.getByLabelText("Description 1:0:1"), {
    target: { value: "Investigator correction retained" },
  })
  fireEvent.change(screen.getByLabelText("Reason 1:0:1"), {
    target: { value: "Checked the source" },
  })
}

it("keeps ignored receipts and restored corrections in review without navigating to empty Transactions or deleting the draft", async () => {
  const onImported = await mount()
  editDescription()
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  )
  await screen.findByRole("heading", { name: "Duplicate - Ignored by system" })
  expect(onImported).not.toHaveBeenCalled()
  expect(screen.queryByText(/Statement balances saved/)).not.toBeInTheDocument()
  expect(screen.getByLabelText("Description 1:0:1")).toHaveValue(
    "Investigator correction retained"
  )
  fireEvent(window, new Event("pagehide"))
  const saved = sessionStorage.getItem(
    `loupe-statement-review:reviewer:${caseId}:${fileId}:${revision}`
  )
  expect(saved).toContain("Investigator correction retained")
  expect(
    screen.getByRole("button", { name: "Restore for comparison" })
  ).toBeVisible()
  duplicateResponse = Promise.resolve({
    case_id: caseId,
    evidence_file_id: fileId,
    statement_id: reading.statement_id,
    duplicate_disposition: {
      ...ignored,
      revision: "f".repeat(64),
      status: "restored",
      label: "Restored for review",
      reason: "Compare the investigator's source correction.",
    },
  })
  fireEvent.change(
    screen.getByLabelText("Reason for restoring to review (optional)"),
    { target: { value: "Compare the investigator's source correction." } }
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Restore for comparison" })
  )
  await screen.findByRole("heading", { name: "Restored for review" })
  expect(onImported).not.toHaveBeenCalled()
  expect(screen.getByLabelText("Description 1:0:1")).toBeEnabled()
  expect(screen.getByLabelText("Description 1:0:1")).toHaveValue(
    "Investigator correction retained"
  )
  expect(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  ).toBeEnabled()
})

it("does not install a late automatic duplicate decision after the investigator edits the draft", async () => {
  let resolve!: (value: unknown) => void
  duplicateResponse = new Promise((done) => {
    resolve = done
  })
  vi.mocked(useStatementCoverageReview).mockReturnValue({
    data: {
      available: true,
      candidates: [],
      matching_statement: true,
      revision: "d".repeat(64),
    },
    pending: false,
    error: undefined,
    retry: vi.fn(),
  })
  await mount()
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      expect.stringContaining("/duplicate-disposition?"),
      expect.anything()
    )
  )
  editDescription()
  resolve({
    case_id: caseId,
    evidence_file_id: fileId,
    statement_id: reading.statement_id,
    duplicate_disposition: ignored,
  })
  await waitFor(() =>
    expect(
      screen.queryByText(/Checking whether this statement/)
    ).not.toBeInTheDocument()
  )
  expect(
    screen.queryByRole("heading", { name: "Duplicate - Ignored by system" })
  ).not.toBeInTheDocument()
  expect(screen.getByLabelText("Description 1:0:1")).toBeEnabled()
  expect(screen.getByLabelText("Description 1:0:1")).toHaveValue(
    "Investigator correction retained"
  )
})

it("does not check the server's older draft while local changes remain unsaved", async () => {
  returnDecision = true
  await mount()
  editDescription()
  const button = screen.queryByRole("button", {
    name: "Check duplicate status",
  })
  if (button) {
    expect(button).toBeDisabled()
    fireEvent.click(button)
  }
  expect(fetchAPI).not.toHaveBeenCalledWith(
    expect.stringContaining("/duplicate-disposition?"),
    expect.anything()
  )
  expect(screen.getByLabelText("Description 1:0:1")).toBeEnabled()
})

it("keeps manual position through checks and import, with an explicit neighbouring boundary for an unread page", async () => {
  await mount()
  fireEvent.click(
    screen.getByRole("button", { name: "Add a missed transaction" })
  )
  const selectors = screen.getAllByLabelText(/^Printed position manual:/)
  const position = selectors[0]
  const rowId = position
    .getAttribute("aria-label")!
    .slice("Printed position ".length)
  fireEvent.change(position, { target: { value: "after:1:0:1" } })
  const lastCheck = vi.mocked(useStatementChecks).mock.calls.at(-1)![2]
  expect(lastCheck.rows).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        id: rowId,
        manual_page: 1,
        source_order_anchor: { relation: "after", row_id: "1:0:1" },
      }),
    ])
  )
  fireEvent(window, new Event("pagehide"))
  const key = `loupe-statement-review:reviewer:${caseId}:${fileId}:${revision}`
  expect(JSON.parse(sessionStorage.getItem(key)!).rows).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        id: rowId,
        source_order_anchor: { relation: "after", row_id: "1:0:1" },
      }),
    ])
  )
  fireEvent.change(screen.getByLabelText("Manual payment source page"), {
    target: { value: "2" },
  })
  const changedPage = vi.mocked(useStatementChecks).mock.calls.at(-1)![2]
  expect(changedPage.rows).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        id: rowId,
        manual_page: 2,
        source_order_anchor: null,
      }),
    ])
  )
  expect(screen.getByLabelText("Corrected transaction date")).toBeVisible()
  expect(screen.getByLabelText("Corrected transaction date")).toBeEnabled()
  const boundary = screen.getAllByRole("option", {
    name: /After the last payment on page 1/,
  })[0]
  fireEvent.change(boundary.parentElement!, {
    target: { value: "after:1:0:1" },
  })
  fireEvent.change(screen.getByLabelText("Corrected transaction date"), {
    target: { value: "2026-01-03" },
  })
  fireEvent.change(screen.getByLabelText("Corrected description"), {
    target: { value: "Payment missed on unread page" },
  })
  fireEvent.change(screen.getByLabelText("Corrected credit"), {
    target: { value: "5.00" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm import of 2 transactions" })
  )
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      expect.stringContaining("/confirm?"),
      expect.objectContaining({
        body: expect.objectContaining({
          rows: expect.arrayContaining([
            expect.objectContaining({
              id: rowId,
              manual_page: 2,
              source_order_anchor: { relation: "after", row_id: "1:0:1" },
              amount_minor: "500",
            }),
          ]),
        }),
      })
    )
  )
})

it.each([
  ["amount", "Corrected credit"],
  ["balance", "Corrected printed balance"],
])(
  "focuses the specific %s correction from the current server blocker",
  async (field, label) => {
    vi.mocked(useStatementChecks).mockReturnValue({
      checks: [],
      admission: {
        can_import: false,
        status: "needs_review",
        revision: "e".repeat(64),
        blockers: [
          {
            kind: "invalid_value",
            field,
            row_id: "1:0:1",
            message: `Check the ${field} printed on this row.`,
            target: {
              kind: "transaction_row",
              field,
              row_id: "1:0:1",
              page: 1,
            },
          },
        ],
      },
      pending: false,
      error: undefined,
      revision: "e".repeat(64),
      retry: vi.fn(),
    })
    await mount()
    expect(
      screen.getByRole("button", { name: "Confirm import of 1 transactions" })
    ).toBeDisabled()
    fireEvent.click(screen.getByRole("button", { name: "Review row" }))
    await waitFor(() => expect(screen.getByLabelText(label)).toHaveFocus())
  }
)

it("replaces an empty earlier import from a batch with one statement decision and no row edits", async () => {
  const { BatchReviewContext } = await import("../lib/batch-review-context")
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/statement-import/") && !options?.method)
      return {
        ...reading,
        current_import: {
          source_document_id: "10000000-0000-4000-8000-000000000010",
          evidence_file_id: "10000000-0000-4000-8000-000000000011",
          revision: "f".repeat(64),
          transaction_count: 0,
        },
      } as never
    return base(url, options)
  })
  const confirm = vi
    .fn()
    .mockResolvedValue({
      case_id: caseId,
      evidence_file_id: fileId,
      source_document_id: "10000000-0000-4000-8000-000000000012",
      transaction_count: 1,
      incomplete_count: 0,
      applied: true,
      created: true,
      issues: [],
    })
  render(
    <QueryClientProvider client={client}>
      <BatchReviewContext.Provider
        value={{ save: vi.fn(), saved: vi.fn(), confirm }}
      >
        <StatementImportPanel caseId={caseId} onImported={vi.fn()} />
      </BatchReviewContext.Provider>
    </QueryClientProvider>
  )
  await screen.findByText(`Review ${reading.filename}`)
  const choice = screen.getByRole("checkbox", {
    name: "Replace the previous import",
  })
  expect(choice).toBeEnabled()
  await page
    .getByRole("checkbox", { name: "Replace the previous import" })
    .click()
  expect(screen.getByLabelText("Reason for detail corrections")).toHaveValue(
    "Use the re-read statement to recover payments missing from the earlier empty import."
  )
  const button = screen.getByRole("button", {
    name: /Import 1 payments and view Transactions/,
  })
  expect(button).toBeEnabled()
  await page.screenshot({ path: "/private/tmp/loupe-reread-choice.png" })
  fireEvent.click(button)
  await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1))
  expect(confirm.mock.calls[0][0]).toMatchObject({
    replaces_source_document_id: "10000000-0000-4000-8000-000000000010",
    replacement_revision: "f".repeat(64),
  })
})
