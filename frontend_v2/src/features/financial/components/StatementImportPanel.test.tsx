import { useStatementCoverageReview } from "../hooks/use-statement-coverage-review"
vi.mock("../hooks/use-statement-coverage-review", async (original) => ({
  ...(await original<
    typeof import("../hooks/use-statement-coverage-review")
  >()),
  useStatementCoverageReview: vi.fn(),
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
import { receiptFixture } from "../lib/payment-document.test-support"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { StatementImportPanel } from "./StatementImportPanel"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"
import { fetchAPI } from "@/lib/api-client"
import { useStatementChecks } from "../hooks/use-statement-checks"
vi.mock("../hooks/use-statement-checks", async (original) => ({
  ...(await original<typeof import("../hooks/use-statement-checks")>()),
  useStatementChecks: vi.fn(),
}))
import { useStatementWorkspace } from "../stores/statement-workspace"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useFinancialDraftStore } from "../stores/financial-drafts"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: vi.fn(() => (
    <div>Original PDF beside editable values</div>
  )),
}))
vi.mock("./PdfReviewIntake", () => ({ PdfReviewIntake: () => null }))
const data = {
  case_id: "case",
  evidence_file_id: "file",
  filename: "statement.pdf",
  currency: "EUR",
  revision: "a".repeat(64),
  metadata: {
    holder: "Example Ltd",
    account_number: "12345",
    institution: "Example Bank",
    period: "January 2023",
    period_start: "2023-01-01",
    period_end: "2023-01-31",
  },
  rows: [
    {
      id: "1:0:0",
      page_number: 1,
      table_index: 0,
      row_index: 0,
      source_cells: [{ column_index: 0, expected_text: "Date", locator: {} }],
      fields: {},
      issues: [] as string[],
      excluded: true,
      kind: "header",
    },
    {
      id: "1:0:1",
      page_number: 1,
      table_index: 0,
      row_index: 1,
      source_cells: [
        { column_index: 0, expected_text: "2023-01-02", locator: {} },
      ],
      fields: {
        date: "2023-01-02",
        description: "Payment",
        amount_minor: "12500",
        direction: "credit",
        balance: "12500",
        counterparty: "Example payer",
      },
      issues: [] as string[],
      excluded: false,
      kind: "transaction",
    },
  ],
  issues: [],
  transaction_count: 1,
  needs_attention: 0,
}
let sent: unknown[] = [],
  failure = false
function mount() {
  const done = vi.fn()
  render(
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
      <StatementImportPanel caseId="case" onImported={done} />
    </QueryClientProvider>
  )
  return done
}
async function open(corrections = true) {
  fireEvent.click(screen.getByRole("button", { name: "Import a statement" }))
  await screen.findByRole("option", { name: "statement.pdf" })
  fireEvent.change(screen.getByLabelText("Uploaded statement"), {
    target: { value: "file" },
  })
  await screen.findByText("Review statement.pdf")
  if (corrections)
    fireEvent.click(
      screen.getByText("Show corrections and import choices", {
        selector: "button",
      })
    )
}
beforeEach(() => {
  useFinancialDraftStore.setState({ drafts: {} })
  vi.mocked(useStatementCoverageReview).mockReturnValue({
    data: { available: true, candidates: [], revision: "d".repeat(64) },
    pending: false,
    error: undefined,
    retry: vi.fn(),
  })
  vi.mocked(useStatementChecks).mockReturnValue({
    admission: {
      can_import: true,
      status: "reconciled",
      revision: "c".repeat(64),
      blockers: [],
    },
    checks: [],
    pending: false,
    error: undefined,
    revision: "c".repeat(64),
    retry: vi.fn(),
  })
  useAuthStore.setState({ user: null })
  sessionStorage.clear()
  useStatementWorkspace.setState({
    selections: {},
    reviewChoices: {},
    pages: {},
    sectionSearches: {},
  })
  sent = []
  failure = false
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (String(url).startsWith("/api/evidence?"))
      return {
        files: [
          {
            id: "file",
            case_id: "case",
            original_filename: "statement.pdf",
            status: "processed",
          },
        ],
      } as never
    if (String(url).includes("/confirm?")) {
      if (failure) throw Error("Source changed. Reload review.")
      sent.push(options?.body)
      return {
        case_id: "case",
        evidence_file_id: "file",
        transaction_count: 1,
        applied: true,
      } as never
    }
    return data as never
  })
})
it("keeps manual rows while completing amounts and preserves review filters across adding and reopening", async () => {
  const implementation = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    const result = await implementation(url, options)
    return result === data ? ({ ...data, page_numbers: [1] } as never) : result
  })
  mount()
  await open()
  fireEvent.click(screen.getByLabelText("Show problems and edits only"))
  expect(screen.getByLabelText("Show excluded rows")).not.toBeChecked()
  fireEvent.click(
    screen.getByRole("button", { name: "Add a missed transaction" })
  )
  const debit = screen.getByLabelText(/^Debit manual:/)
  fireEvent.change(debit, { target: { value: "123.45" } })
  fireEvent.change(screen.getByLabelText(/^Date manual:/), {
    target: { value: "2023-01-03" },
  })
  fireEvent.change(screen.getByLabelText(/^Description manual:/), {
    target: { value: "Manually read payment" },
  })
  expect(debit).toBeVisible()
  expect(screen.getByLabelText("Show excluded rows")).not.toBeChecked()
  expect(screen.getByLabelText("Show problems and edits only")).toBeChecked()
  fireEvent.click(screen.getByRole("button", { name: "Done editing this row" }))
  fireEvent.click(
    screen.getByRole("button", { name: "Add a missed transaction" })
  )
  expect(screen.getAllByLabelText(/^Debit manual:/)).toHaveLength(2)
  expect(screen.getByDisplayValue("Manually read payment")).toBeVisible()
  cleanup()
  mount()
  await screen.findByText("Review statement.pdf")
  fireEvent.click(
    screen.getByRole("button", { name: "Show corrections and import choices" })
  )
  expect(screen.getByLabelText("Show excluded rows")).not.toBeChecked()
  expect(screen.getByLabelText("Show problems and edits only")).toBeChecked()
})
it("imports directly from a batch review, carrying account edits into the visible receipt", async () => {
  const { BatchReviewContext } = await import("../lib/batch-review-context")
  const save = vi.fn(),
    saved = vi.fn(),
    done = vi.fn()
  const confirmBatch = vi.fn().mockResolvedValue({
    case_id: "case",
    evidence_file_id: "file",
    source_document_id: "new-source",
    account_id: "new-account",
    transaction_count: 1,
    incomplete_count: 0,
    record_count: 1,
    applied: true,
  })
  useStatementWorkspace.getState().select("anonymous:case", "file")
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <BatchReviewContext.Provider
        value={{ save, saved, confirm: confirmBatch }}
      >
        <StatementImportPanel caseId="case" onImported={done} />
      </BatchReviewContext.Provider>
    </QueryClientProvider>
  )
  await screen.findByText("Review statement.pdf")
  fireEvent.change(screen.getByLabelText("Account holder"), {
    target: { value: "Reviewed holder" },
  })
  fireEvent.click(
    screen.getByRole("button", {
      name: "Import 1 payments and view Transactions",
    })
  )
  await waitFor(() =>
    expect(done).toHaveBeenCalledWith(
      expect.objectContaining({
        source_document_id: "new-source",
        transaction_count: 1,
      })
    )
  )
  expect(confirmBatch).toHaveBeenCalledWith(
    expect.objectContaining({ holder: "Reviewed holder" })
  )
  expect(save).not.toHaveBeenCalled()
  expect(saved).not.toHaveBeenCalled()
})

it("uses automatic currency and replaces an old EUR choice with the detected USD reading", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  useStatementWorkspace.getState().setReviewChoice("anonymous:case:file", {
    currency: "EUR",
  })
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (!url.includes("/statement-import/file?")) return base(url, options)
    const manual = new URL(url, "http://test").searchParams.get("currency")
    return {
      ...data,
      currency: manual || "USD",
      detected_currency: "USD",
      revision: (manual ? "a" : "b").repeat(64),
      rows: [
        data.rows[0],
        {
          ...data.rows[1],
          fields: {
            ...data.rows[1].fields,
            amount_minor: manual ? "" : "2119",
          },
          issues: manual
            ? [
                'The statement shows "$21.19", but this review uses EUR. Change the statement currency.',
              ]
            : [],
        },
      ],
    } as never
  })
  mount()
  await open()
  expect(screen.getByLabelText("Credit 1:0:1")).toHaveValue("")
  expect(
    screen.getByText(/The automatic reading suggests USD; this review uses EUR/)
  ).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Use USD from statement" })
  )
  await screen.findByText("Detected from statement")
  fireEvent.click(screen.getByRole("button", { name: "Edit import values" }))
  expect(screen.getByLabelText("Credit 1:0:1")).toHaveValue("21.19")
  expect(screen.queryByText(/review uses EUR/)).not.toBeInTheDocument()
  expect(
    useStatementWorkspace.getState().reviewChoices["anonymous:case:file"]
      .currency
  ).toBe("")
  expect(sent).toEqual([])
})

it("opens the parent payment editor when a wrapped money cell is selected", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  const locator = (rect: number[]) => ({
    kind: "page_rectangle",
    page: 1,
    rect,
    page_size: [600000, 800000],
    units: "millipoints",
    space: "pdf_displayed",
  })
  const moneyCells = [
    {
      column_index: 0,
      expected_text: "125.00",
      locator: locator([310000, 240000, 330000, 248000]),
    },
    {
      column_index: 1,
      expected_text: "125.00 balance",
      locator: locator([350000, 240000, 370000, 248000]),
    },
  ]
  const payment = {
    ...data.rows[1],
    fields: {
      ...data.rows[1].fields,
      statement_layout: "andrews-share-statement",
    },
    source_cells: [
      {
        column_index: 0,
        expected_text: "2023-01-02",
        locator: locator([15000, 228000, 45000, 236000]),
      },
    ],
    value_sources: {
      amount: {
        page_number: 1,
        table_index: 0,
        row_index: 2,
        source_cell: moneyCells[0],
      },
      balance: {
        page_number: 1,
        table_index: 0,
        row_index: 2,
        source_cell: moneyCells[1],
      },
    },
  }
  const proposal = {
    ...structuredClone(data),
    rows: [
      data.rows[0],
      payment,
      {
        id: "1:0:2",
        page_number: 1,
        table_index: 0,
        row_index: 2,
        source_cells: moneyCells,
        fields: {
          statement_layout: "andrews-share-statement",
          parent_transaction_id: payment.id,
        },
        issues: [],
        excluded: true,
        kind: "continuation",
      },
    ],
  }
  vi.mocked(fetchAPI).mockImplementation(async (url, options) =>
    String(url).includes("/statement-import/file?")
      ? (proposal as never)
      : base(url, options)
  )
  mount()
  await open()
  expect(
    vi.mocked(TransactionSourceHighlight).mock.lastCall?.[0].locatorPayload
  ).toEqual(locator([15000, 228000, 370000, 248000]))
  fireEvent.click(screen.getByRole("button", { name: "125.00 balance" }))
  expect(
    vi.mocked(TransactionSourceHighlight).mock.lastCall?.[0].locatorPayload
  ).toEqual(moneyCells[1].locator)
  fireEvent.click(await screen.findByRole("button", { name: "Edit this row" }))
  expect(
    screen.getByRole("region", { name: "Edit selected statement row" })
  ).toBeTruthy()
  cleanup()
})
it("imports completed Merrick years through the normal recorded correction request", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  const proposal = {
    ...structuredClone(data),
    statement_id: "m".repeat(64),
    statement_choices: [
      {
        id: "m".repeat(64),
        institution: "Merrick Bank",
        layout_id: "merrick-card",
        account_reference: "12345",
        period_start: "",
        period_end: "",
        page_numbers: [1],
      },
    ],
  }
  proposal.rows[1].fields.date = ""
  proposal.rows[1].source_cells[0].expected_text = "01/02"
  proposal.rows[1].issues = [
    "Check the full date. The printed statement context could not resolve its year.",
  ]
  vi.mocked(fetchAPI).mockImplementation(async (url, options) =>
    String(url).includes("/statement-import/file?")
      ? (proposal as never)
      : base(url, options)
  )
  mount()
  await open()
  fireEvent.click(screen.getByRole("button", { name: "Correct several rows" }))
  fireEvent.change(screen.getByLabelText("Correction"), {
    target: { value: "date_year" },
  })
  fireEvent.change(screen.getByLabelText("Printed statement closing date"), {
    target: { value: "2023-01-25" },
  })
  fireEvent.change(
    screen.getByLabelText("Note about these corrections (optional)"),
    {
      target: { value: "Year checked against statement heading" },
    }
  )
  fireEvent.click(
    screen.getByRole("button", {
      name: "Select 1 readable dates missing a year",
    })
  )
  fireEvent.click(screen.getByRole("button", { name: "Preview corrections" }))
  fireEvent.click(
    screen.getByRole("button", { name: "Apply corrections to 1 rows" })
  )
  expect(screen.getByLabelText("Date 1:0:1")).toHaveValue("2023-01-02")
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  )
  await waitFor(() => expect(sent).toHaveLength(1))
  expect(sent[0]).toMatchObject({
    rows: expect.arrayContaining([
      expect.objectContaining({
        id: "1:0:1",
        date: "2023-01-02",
        reason: expect.stringContaining(
          "closing date 2023-01-25; printed day/month 01/02"
        ),
      }),
    ]),
  })
  expect(proposal.rows[1].fields.date).toBe("")
})

it("retains an additional printed date without requiring a per-row decision", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  const proposal = structuredClone(data)
  Object.assign(proposal.rows[1].fields, { additional_printed_date: "01/01" })
  vi.mocked(fetchAPI).mockImplementation(async (url, options) =>
    String(url).includes("/statement-import/file?")
      ? (proposal as never)
      : base(url, options)
  )
  mount()
  await open()
  expect(screen.getByText(/Also printed: 01\/01/)).toBeInTheDocument()
  expect(screen.getByLabelText("Date 1:0:1")).toHaveValue("2023-01-02")
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  )
  await waitFor(() => expect(sent).toHaveLength(1))
  expect(sent[0]).toMatchObject({
    rows: expect.arrayContaining([
      expect.objectContaining({ id: "1:0:1", date: "2023-01-02", reason: "" }),
    ]),
  })
})

it("imports recognised undated interest without inventing a date and supports a later date correction", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  const charge = structuredClone(data)
  Object.assign(charge.rows[1], {
    fields: {
      date_basis: "statement_end_ordering_only",
      description: "Interest Charge on Purchases",
      amount_minor: "12500",
      direction: "debit",
    },
    source_cells: [
      {
        column_index: 0,
        expected_text: "Interest Charge on Purchases",
        locator: {},
      },
      { column_index: 1, expected_text: "125.00", locator: {} },
    ],
  })
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    String(url).includes("/statement-import/file?")
      ? Promise.resolve(charge as never)
      : base(url, options)
  )
  mount()
  await open()
  expect(screen.getByText("Date not printed")).toBeInTheDocument()
  const confirm = screen.getByRole("button", {
    name: "Confirm import of 1 transactions",
  })
  expect(confirm).toBeEnabled()
  fireEvent.change(screen.getByLabelText("Date 1:0:1"), {
    target: { value: "2023-01-30" },
  })
  expect(screen.queryByText("Date not printed")).not.toBeInTheDocument()
  expect(confirm).toBeEnabled()
  fireEvent.change(screen.getByLabelText("Date 1:0:1"), {
    target: { value: "" },
  })
  expect(confirm).toBeEnabled()
  fireEvent.click(confirm)
  await waitFor(() => expect(sent).toHaveLength(1))
  expect((sent[0] as { rows: unknown[] }).rows[1]).toMatchObject({
    date: "",
    date_unprinted: true,
    reason: "",
  })
})
it("saves an incomplete individual review to the case and restores it without browser storage", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  let progress: Record<string, unknown> | null = null
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (String(url).includes("/progress?")) {
      const body = options!.body as {
        request: Record<string, unknown>
        expected_review_revision: string
      }
      expect(body.expected_review_revision).toBe(
        progress ? "saved-revision" : "initial"
      )
      progress = {
        request: body.request,
        review_revision: "saved-revision",
        saved_at: "2026-09-17T10:00:00Z",
        saved_by: { name: "Reviewer" },
      }
      return { case_id: "case", evidence_file_id: "file", ...progress } as never
    }
    if (String(url).includes("statement-import/file?"))
      return { ...data, saved_review: progress } as never
    return base(url, options)
  })
  mount()
  await open()
  fireEvent.change(screen.getByLabelText("Date 1:0:1"), {
    target: { value: "" },
  })
  fireEvent.change(screen.getByLabelText("Description 1:0:1"), {
    target: { value: "Corrected source description" },
  })
  fireEvent.change(screen.getByLabelText("Account number"), {
    target: { value: "0012345" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Save account details" }))
  await screen.findByText(
    "Progress saved to the case. You can reopen this statement on another device."
  )
  expect(sent).toHaveLength(0)
  cleanup()
  sessionStorage.clear()
  mount()
  await screen.findByText("Review statement.pdf")
  fireEvent.click(
    screen.getByText("Show corrections and import choices", {
      selector: "button",
    })
  )
  expect(screen.getByLabelText("Account number")).toHaveValue("0012345")
  expect(screen.getByLabelText("Date 1:0:1")).toHaveValue("")
  expect(screen.getByLabelText("Description 1:0:1")).toHaveValue(
    "Corrected source description"
  )
  expect(
    screen.getByRole("button", { name: /Confirm import of/ })
  ).toBeEnabled()
  fireEvent.click(screen.getByRole("button", { name: "Save progress" }))
  await screen.findByText(
    "Progress saved to the case. You can reopen this statement on another device."
  )
})

it("retains current edits when another reviewer has saved first", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (String(url).includes("/progress?"))
      throw Error("Another reviewer saved this statement.")
    return base(url, options)
  })
  mount()
  await open()
  fireEvent.change(screen.getByLabelText("Description 1:0:1"), {
    target: { value: "My retained correction" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Save progress" }))
  await screen.findAllByText(/Another reviewer saved this statement/)
  expect(screen.getByLabelText("Description 1:0:1")).toHaveValue(
    "My retained correction"
  )
  expect(sent).toHaveLength(0)
})
it("shows earlier corrections when a reprocessed reading differs and requires a comparison", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (String(url).includes("statement-import/file?"))
      return {
        ...data,
        previous_saved_review: {
          evidence_file_id: "previous-file",
          filename: "statement.pdf",
          request: {
            expected_revision: "b".repeat(64),
            holder: "Earlier holder",
            account_number: "12345",
            institution: "Example Bank",
            period_start: "2023-01-01",
            period_end: "2023-01-31",
            rows: [
              {
                id: "1:0:1",
                date: "2023-01-02",
                description: "Earlier saved description",
                direction: "credit",
                amount_minor: "12500",
                balance_minor: null,
                counterparty: "",
                excluded: false,
                reason: "Earlier source check",
              },
            ],
          },
        },
      } as never
    return base(url, options)
  })
  mount()
  await open()
  expect(
    screen.getByRole("region", { name: "Previous saved review" })
  ).toHaveTextContent("Earlier saved description")
  expect(screen.getByLabelText("Description 1:0:1")).toHaveValue("Payment")
  expect(screen.getByRole("button", { name: "Save progress" })).toBeDisabled()
  expect(
    screen.getByRole("button", { name: /Confirm import of/ })
  ).toBeDisabled()
  fireEvent.click(
    screen.getByLabelText("I have compared the previous saved review")
  )
  expect(screen.getByRole("button", { name: "Save progress" })).toBeEnabled()
})
it("opens an excluded duplicate as a source without offering another import", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) =>
    String(url).includes("statement-import")
      ? ({
          ...data,
          current_import: {
            source_document_id: "excluded",
            evidence_file_id: "file",
            revision: "b".repeat(64),
            transaction_count: 0,
            excluded_as_duplicate: true,
            retained_filename: "retained.pdf",
          },
        } as never)
      : base(url, options)
  )
  const done = mount()
  fireEvent.click(screen.getByRole("button", { name: "Import a statement" }))
  await screen.findByRole("option", { name: "statement.pdf" })
  fireEvent.change(screen.getByLabelText("Uploaded statement"), {
    target: { value: "file" },
  })
  await screen.findByText("Review statement.pdf")
  expect(
    screen.getByText("This copy was excluded as a duplicate")
  ).toBeVisible()
  expect(screen.getByText("Retained file: retained.pdf")).toBeVisible()
  expect(screen.getByText("Original PDF beside editable values")).toBeVisible()
  expect(
    screen.getByRole("link", { name: "Review duplicate decision" })
  ).toHaveAttribute("href", "/cases/case/financial?view=ledger")
  expect(
    screen.queryByRole("button", {
      name: /Confirm import|Edit imported|Open imported|Read again|Add a missed transaction|Show corrections and import choices/,
    })
  ).not.toBeInTheDocument()
  expect(screen.queryByText(/transactions to import/)).not.toBeInTheDocument()
  expect(
    screen.queryByRole("textbox", { name: "Account holder" })
  ).not.toBeInTheDocument()
  expect(sent).toEqual([])
  expect(done).not.toHaveBeenCalled()
})
it("opens and focuses a flagged row's import choice while retaining another correction", async () => {
  const flagged = {
    ...data,
    rows: [
      ...data.rows,
      {
        ...data.rows[0],
        id: "1:0:15",
        row_index: 15,
        source_cells: [
          {
            column_index: 0,
            expected_text: "Printed footer",
            locator: { kind: "page_only", page: 1 },
          },
        ],
        kind: "unresolved",
        excluded: false,
        issues: ["Check this row"],
      },
    ],
  }
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) =>
    String(url).includes("statement-import")
      ? (flagged as never)
      : base(url, options)
  )
  mount()
  await open()
  fireEvent.change(screen.getByLabelText("Credit 1:0:1"), {
    target: { value: "130.00" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Hide corrections and import choices" })
  )
  fireEvent.click(
    screen.getAllByRole("button", { name: "Review this row" }).at(-1)!
  )
  const editor = await screen.findByRole("region", {
    name: "Edit selected statement row",
  })
  expect(editor).toBeVisible()
  expect(screen.getByText("Original PDF beside editable values")).toBeVisible()
  fireEvent.click(screen.getByLabelText("Include this transaction"))
  fireEvent.change(screen.getByLabelText("Reason for this row correction"), {
    target: { value: "Printed footer, not a payment." },
  })
  expect(screen.getByLabelText("Include this transaction")).not.toBeChecked()
  fireEvent.click(screen.getByRole("button", { name: "Done editing this row" }))
  fireEvent.click(
    screen.getByText("Show corrections and import choices", {
      selector: "button",
    })
  )
  expect(screen.getByLabelText("Credit 1:0:1")).toHaveValue("130.00")
  expect(sent).toEqual([])
})
it("automatically fills a statement and imports once", async () => {
  const done = mount()
  await open()
  expect(screen.getByLabelText("Account holder")).toHaveValue("Example Ltd")
  expect(screen.getByLabelText("Date 1:0:1")).toHaveValue("2023-01-02")
  expect(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  ).toBeEnabled()
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  )
  await waitFor(() => expect(done).toHaveBeenCalledTimes(1))
  expect(sent).toHaveLength(1)
  expect(sent[0]).toMatchObject({
    account_number: "12345",
    rows: [
      { id: "1:0:0", excluded: true },
      {
        id: "1:0:1",
        amount_minor: "12500",
        balance_minor: "12500",
        excluded: false,
      },
    ],
  })
})

it("edits posting and value dates separately and records a reason without changing the transaction date", async () => {
  const multiple = structuredClone(data)
  Object.assign(multiple.rows[1].fields, {
    booking_date: "2023-01-03",
    value_date: "2023-01-04",
    date_column: "0",
    booking_date_column: "1",
    value_date_column: "2",
  })
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    String(url).includes("statement-import") &&
    !String(url).includes("/confirm?")
      ? Promise.resolve(multiple as never)
      : base(url, options)
  )
  const done = mount()
  await open()
  expect(screen.getByLabelText("Posting date 1:0:1")).toHaveValue("2023-01-03")
  expect(screen.getByLabelText("Value date 1:0:1")).toHaveValue("2023-01-04")
  fireEvent.change(screen.getByLabelText("Posting date 1:0:1"), {
    target: { value: "2023-01-05" },
  })
  fireEvent.change(screen.getByLabelText("Value date 1:0:1"), {
    target: { value: "" },
  })
  expect(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  ).toBeEnabled()
  expect(screen.getByLabelText("Date 1:0:1")).toHaveValue("2023-01-02")
  fireEvent.change(screen.getByLabelText("Reason 1:0:1"), {
    target: { value: "Checked posting date; value date cannot be confirmed." },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  )
  await waitFor(() => expect(done).toHaveBeenCalledTimes(1))
  expect(sent[0]).toMatchObject({
    rows: [
      { id: "1:0:0" },
      {
        id: "1:0:1",
        date: "2023-01-02",
        date_values: { booking_date: "2023-01-05", value_date: "" },
      },
    ],
  })
})

it("offers the missing transaction date separately when the posting date was read", async () => {
  const multiple = structuredClone(data)
  delete (multiple.rows[1].fields as Record<string, unknown>).date
  Object.assign(multiple.rows[1].fields, {
    booking_date: "2023-01-03",
    date_column: "0",
    booking_date_column: "1",
  })
  multiple.rows[1].issues = ["Check the transaction date."]
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    String(url).includes("statement-import") &&
    !String(url).includes("/confirm?")
      ? Promise.resolve(multiple as never)
      : base(url, options)
  )
  const done = mount()
  await open()
  expect(screen.getByLabelText("Date 1:0:1")).toHaveValue("2023-01-03")
  expect(screen.getByLabelText("Transaction date 1:0:1")).toHaveValue("")
  fireEvent.change(screen.getByLabelText("Transaction date 1:0:1"), {
    target: { value: "2023-01-02" },
  })
  fireEvent.change(screen.getByLabelText("Reason 1:0:1"), {
    target: { value: "Read the transaction date from the PDF." },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  )
  await waitFor(() => expect(done).toHaveBeenCalledTimes(1))
  expect(sent[0]).toMatchObject({
    rows: [
      { id: "1:0:0" },
      { id: "1:0:1", date: "2023-01-03", date_values: { date: "2023-01-02" } },
    ],
  })
})

it("imports unknown directions and allows corrections without a mandatory note", async () => {
  const unknown = structuredClone(data)
  delete (unknown.rows[1].fields as Record<string, unknown>).direction
  unknown.rows[1].issues = ["The payment's minus sign could not be read."]
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    String(url).includes("statement-import") &&
    !String(url).includes("/confirm?")
      ? Promise.resolve(unknown as never)
      : base(url, options)
  )
  mount()
  await open()
  expect(screen.getByLabelText("Credit 1:0:1")).toHaveValue("")
  expect(screen.getByLabelText("Debit 1:0:1")).toHaveValue("")
  expect(screen.getByText(/Totals are incomplete/)).toBeVisible()
  const confirm = screen.getByRole("button", {
    name: "Confirm import of 1 transactions",
  })
  expect(confirm).toBeEnabled()
  fireEvent.change(screen.getByLabelText("Credit 1:0:1"), {
    target: { value: "125.00" },
  })
  expect(confirm).toBeEnabled()
  fireEvent.change(screen.getByLabelText("Reason 1:0:1"), {
    target: { value: "Checked the original payment marker" },
  })
  expect(confirm).toBeEnabled()
  expect(screen.queryByText(/Totals are incomplete/)).not.toBeInTheDocument()
  fireEvent.click(confirm)
  await waitFor(() => expect(sent).toHaveLength(1))
  expect(sent[0]).toMatchObject({
    rows: [{ direction: null }, { direction: "credit", amount_minor: "12500" }],
  })
})

it("saves the latest edit on page exit before the delayed save can run", async () => {
  useAuthStore.setState({
    user: {
      id: "reviewer",
      username: "reviewer",
      name: "Reviewer",
      role: null,
    },
  })
  mount()
  await open()
  fireEvent.change(screen.getByLabelText("Credit 1:0:1"), {
    target: { value: "125.50" },
  })
  fireEvent.change(screen.getByLabelText("Reason 1:0:1"), {
    target: { value: "Checked just before refreshing" },
  })
  fireEvent(window, new Event("pagehide"))
  const key = `loupe-statement-review:reviewer:case:file:${data.revision}`
  const saved = JSON.parse(sessionStorage.getItem(key)!)
  expect(
    saved.rows.find((row: { id: string }) => row.id === "1:0:1")
  ).toMatchObject({
    amount_minor: "12550",
    reason: "Checked just before refreshing",
  })
})

it("opens card-balance corrections from the summary and submits the printed sign", async () => {
  const card = {
    ...data,
    metadata: {
      ...data.metadata,
      account_type: "credit_card",
      balance_convention: "liability_owed",
    },
    rows: [
      ...data.rows,
      {
        ...data.rows[0],
        id: "1:0:2",
        row_index: 2,
        kind: "balance",
        fields: {
          description: "Opening Balance",
          balance: "100000",
          balance_column: "1",
          balance_convention: "liability_owed",
        },
        source_cells: [
          {
            column_index: 1,
            expected_text: "$1,000.00",
            locator: { kind: "page_only", page: 1 },
          },
        ],
      },
    ],
  }
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    String(url).includes("statement-import") &&
    !String(url).includes("/confirm?")
      ? Promise.resolve(card as never)
      : base(url, options)
  )
  mount()
  await open()
  fireEvent.click(
    screen.getByRole("button", { name: "Hide corrections and import choices" })
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Edit opening amount owed" })
  )
  const balance = await screen.findByLabelText("Balance 1:0:2")
  expect(balance).toHaveValue("1000.00")
  expect(screen.queryByLabelText("Include row 1:0:0")).not.toBeInTheDocument()
  expect(screen.getByLabelText("Show excluded rows")).not.toBeChecked()
  expect(screen.getByLabelText("Include row 1:0:2")).toBeDisabled()
  fireEvent.change(balance, { target: { value: "1001.00" } })
  fireEvent.change(screen.getByLabelText("Reason 1:0:2"), {
    target: { value: "Corrected against the PDF" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  )
  await waitFor(() => expect(sent.length).toBe(1))
  const request = sent[0] as {
    rows: { id: string; balance_minor: string; excluded: boolean }[]
  }
  expect(
    request.rows.find((r: { id: string }) => r.id === "1:0:2")
  ).toMatchObject({ balance_minor: "100100", excluded: true })
})

it("keeps repeated statement balances editable instead of calling them missing", async () => {
  const repeated = {
    ...data,
    metadata: {
      ...data.metadata,
      account_type: "credit_card",
      balance_convention: "liability_owed",
    },
    rows: [
      ...data.rows,
      ...[1, 4].map((page) => ({
        ...data.rows[0],
        id: `${page}:0:2`,
        page_number: page,
        row_index: 2,
        kind: "balance",
        fields: {
          description: "Opening Balance",
          balance: "100000",
          balance_column: "1",
        },
        source_cells: [
          {
            column_index: 1,
            expected_text: "$1,000.00",
            locator: { kind: "page_only", page },
          },
        ],
      })),
    ],
  }
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    String(url).includes("statement-import") &&
    !String(url).includes("/confirm?")
      ? Promise.resolve(repeated as never)
      : base(url, options)
  )
  mount()
  await open()
  expect(screen.getByText(/Found 2 readings/)).toBeInTheDocument()
  fireEvent.click(
    screen.getByRole("button", { name: "Hide corrections and import choices" })
  )
  fireEvent.click(
    screen.getByRole("button", {
      name: "Edit opening amount owed on page 4, row 3",
    })
  )
  fireEvent.change(await screen.findByLabelText("Balance 4:0:2"), {
    target: { value: "" },
  })
  fireEvent.change(screen.getByLabelText("Reason 4:0:2"), {
    target: { value: "Page 4 repeats the statement on page 1" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  )
  await waitFor(() => expect(sent.length).toBe(1))
  const request = sent[0] as {
    rows: { id: string; balance_minor: string | null; excluded: boolean }[]
  }
  expect(request.rows.find((r) => r.id === "1:0:2")).toMatchObject({
    balance_minor: "100000",
    excluded: true,
  })
  expect(request.rows.find((r) => r.id === "4:0:2")).toMatchObject({
    balance_minor: null,
    excluded: true,
  })
})

it("keeps recognised information pages available without asking to correct them as payments", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    String(url).includes("/statement-import/file?")
      ? Promise.resolve({
          ...data,
          page_numbers: [1, 2],
          information_pages: [{ page_number: 2, kind: "privacy_notice" }],
        } as never)
      : base(url, options)
  )
  mount()
  await open()
  fireEvent.click(screen.getByText("Inspect another page of the original PDF"))
  expect(
    screen.getByText(/information pages contain supporting material/)
  ).toBeVisible()
  expect(
    screen.getByRole("option", { name: "Page 2 · information page" })
  ).toBeInTheDocument()
  expect(
    screen.queryByText(/pages need a coverage check/)
  ).not.toBeInTheDocument()
  expect(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  ).toBeEnabled()
  fireEvent.change(screen.getByLabelText("Original PDF page"), {
    target: { value: "2" },
  })
  expect(screen.getByLabelText("Original PDF page")).toHaveValue("2")
})

it("opens unassigned payments for a reviewed move without offering a direct import", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  const choice = {
    institution: "Example Bank",
    account_reference: "",
    period_start: "2023-01-01",
    period_end: "2023-01-31",
    page_numbers: [1],
  }
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    String(url).includes("/statement-import/file?")
      ? Promise.resolve({
          ...data,
          page_numbers: [1],
          assignment_only: true,
          printed_main_account: "12345",
          statement_id: "orphan",
          metadata: { ...data.metadata, holder: "", account_number: "" },
          statement_choices: [
            { ...choice, id: "orphan", assignment_only: true },
            { ...choice, id: "other-orphan", assignment_only: true },
            {
              ...choice,
              id: "target",
              account_reference: "12345 / Share 0040",
            },
          ],
        } as never)
      : base(url, options)
  )
  mount()
  await open()
  expect(
    screen.getByRole("region", { name: "Unassigned payments" })
  ).toHaveTextContent("This page cannot be imported on its own")
  expect(screen.getByLabelText("Correction")).toHaveValue("reassign")
  expect(
    screen
      .getByLabelText("Move to account and period")
      .querySelectorAll("option")
  ).toHaveLength(2)
  expect(
    screen.queryByRole("button", { name: /Confirm import/ })
  ).not.toBeInTheDocument()
  expect(
    screen.queryByRole("textbox", { name: "Account holder" })
  ).not.toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "Add a missed transaction" })
  ).not.toBeInTheDocument()
  expect(
    screen.getByText("Original PDF beside editable values")
  ).toBeInTheDocument()
})

it("explains an unassigned page with no recognised destination instead of presenting an empty move", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    String(url).includes("/statement-import/file?")
      ? Promise.resolve({
          ...data,
          page_numbers: [1],
          assignment_only: true,
          printed_main_account: "12345",
        } as never)
      : base(url, options)
  )
  mount()
  await open()
  expect(
    screen.getByText(/No destination account was recognised/)
  ).toBeVisible()
  expect(
    screen.queryByLabelText("Move to account and period")
  ).not.toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: /Confirm import/ })
  ).not.toBeInTheDocument()
})

it("removes empty correction controls when all unassigned payments have been moved", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    String(url).includes("/statement-import/file?")
      ? Promise.resolve({
          ...data,
          assignment_only: true,
          printed_main_account: "12345",
          rows: [],
          transaction_count: 0,
        } as never)
      : base(url, options)
  )
  mount()
  useStatementWorkspace.getState().select("anonymous:case", "file")
  expect(
    await screen.findByText("All payments have been assigned")
  ).toBeVisible()
  expect(
    screen.queryByRole("button", { name: /Select all .* matching rows/ })
  ).toBeNull()
  expect(screen.queryByRole("button", { name: /Confirm import/ })).toBeNull()
})

it("changes the printed page with next and previous controls", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    String(url).startsWith("/api/evidence?")
      ? ({
          files: [
            {
              id: "file",
              case_id: "case",
              original_filename: "statement.pdf",
              status: "processed",
            },
          ],
        } as never)
      : ({
          ...data,
          page_numbers: [1, 2],
          rows: [
            ...data.rows,
            {
              ...data.rows[1],
              id: "2:0:1",
              page_number: 2,
              source_cells: [
                {
                  column_index: 0,
                  expected_text: "Second printed page",
                  locator: { kind: "page_only", page: 2 },
                },
              ],
            },
          ],
        } as never)
  )
  mount()
  await open()
  expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Next page" }))
  expect(screen.getByLabelText("Statement viewer page")).toHaveValue("2")
  expect(
    screen.getByRole("button", { name: "Second printed page" })
  ).toBeVisible()
  expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Previous page" }))
  expect(screen.getByLabelText("Statement viewer page")).toHaveValue("1")
  expect(
    screen.queryByRole("button", { name: "Second printed page" })
  ).not.toBeInTheDocument()
})
it("shows the source alongside correction controls and saves the reason", async () => {
  mount()
  await open()
  fireEvent.click(screen.getByRole("button", { name: "View source" }))
  expect(screen.getByText("Original PDF beside editable values")).toBeVisible()
  fireEvent.change(screen.getByLabelText("Credit 1:0:1"), {
    target: { value: "125.50" },
  })
  expect(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  ).toBeEnabled()
  fireEvent.change(screen.getByLabelText("Reason 1:0:1"), {
    target: { value: "Corrected against original" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  )
  await waitFor(() => expect(sent).toHaveLength(1))
  expect(sent[0]).toMatchObject({
    rows: [{}, { amount_minor: "12550", reason: "Corrected against original" }],
  })
})
it("keeps edits after a failed confirmation", async () => {
  failure = true
  mount()
  await open()
  fireEvent.change(screen.getByLabelText("Description 1:0:1"), {
    target: { value: "Corrected description" },
  })
  fireEvent.change(screen.getByLabelText("Reason 1:0:1"), {
    target: { value: "Checked original" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  )
  await screen.findByRole("alert")
  expect(screen.getByLabelText("Description 1:0:1")).toHaveValue(
    "Corrected description"
  )
})

it("requires an explicit replacement decision and reason for an existing import", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (String(url).includes("/statement-import/") && !options?.method)
      return {
        ...data,
        current_import: {
          source_document_id: "previous",
          evidence_file_id: "older-file",
          revision: "b".repeat(64),
          transaction_count: 1,
        },
      } as never
    return base(url, options)
  })
  mount()
  await open()
  const confirm = screen.getByRole("button", {
    name: "Confirm import of 1 transactions",
  })
  expect(confirm).toBeDisabled()
  fireEvent.click(
    screen.getByRole("checkbox", { name: /Replace the previous import/ })
  )
  expect(confirm).toBeDisabled()
  fireEvent.change(screen.getByLabelText("Reason for detail corrections"), {
    target: {
      value: "Checked the corrected extraction against the statement.",
    },
  })
  expect(confirm).toBeEnabled()
  fireEvent.click(confirm)
  await waitFor(() => expect(sent).toHaveLength(1))
  expect(sent[0]).toMatchObject({
    replaces_source_document_id: "previous",
    replacement_revision: "b".repeat(64),
  })
})

it("updates an eligible empty legacy import and opens its usable results", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (
      String(url).includes("/refresh-reading") &&
      options?.method === "POST"
    ) {
      expect(options.body).toEqual({
        expected_revision: "b".repeat(64),
        expected_reading_revision: data.revision,
        currency: "EUR",
      })
      return {
        case_id: "case",
        evidence_file_id: "file",
        source_document_id: "updated",
        account_id: "saved-account",
        transaction_count: 1,
        record_count: 1,
        incomplete_count: 0,
        applied: true,
      } as never
    }
    if (String(url).includes("/statement-import/") && !options?.method)
      return {
        ...data,
        current_import: {
          source_document_id: "previous",
          account_id: "saved-account",
          evidence_file_id: "file",
          revision: "b".repeat(64),
          transaction_count: 0,
          incomplete_count: 250,
          refresh_available: true,
        },
      } as never
    return base(url, options)
  })
  const done = mount()
  await open(false)
  expect(
    screen.getByText(/current reading identifies 1 payments/)
  ).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Save 1 payments to Transactions",
    })
  )
  await waitFor(() =>
    expect(done).toHaveBeenCalledWith(
      expect.objectContaining({
        source_document_id: "updated",
        transaction_count: 1,
        incomplete_count: 0,
      })
    )
  )
})

it("lets an empty legacy import compare an older draft and save its current payments", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (
      String(url).includes("/refresh-reading") &&
      options?.method === "POST"
    ) {
      expect(options.body).toMatchObject({
        compared_review_revision: "c".repeat(64),
      })
      return {
        case_id: "case",
        evidence_file_id: "file",
        source_document_id: "updated",
        transaction_count: 1,
        incomplete_count: 0,
        applied: true,
      } as never
    }
    if (String(url).includes("/statement-import/") && !options?.method)
      return {
        ...data,
        saved_review: {
          review_revision: "c".repeat(64),
          saved_at: "2026-09-20T12:00:00Z",
          saved_by: { name: "Reviewer" },
          request: {
            expected_revision: "older",
            holder: "Saved holder",
            account_number: "00123",
            institution: "Bank",
            period_start: "",
            period_end: "",
            rows: [],
          },
        },
        current_import: {
          source_document_id: "previous",
          evidence_file_id: "file",
          revision: "b".repeat(64),
          transaction_count: 0,
          incomplete_count: 250,
          refresh_available: false,
          refresh_review_required: true,
          refresh_transaction_count: 1,
        },
      } as never
    return base(url, options)
  })
  const done = mount()
  await open(false)
  const save = screen.getByRole("button", {
    name: "Save 1 payments to Transactions",
  })
  expect(save).toBeDisabled()
  expect(
    screen.getAllByRole("region", { name: "Previous saved review" })
  ).toHaveLength(1)
  fireEvent.click(
    screen.getByLabelText("I have compared the previous saved review")
  )
  expect(save).toBeEnabled()
  fireEvent.click(save)
  await waitFor(() =>
    expect(done).toHaveBeenCalledWith(
      expect.objectContaining({ transaction_count: 1 })
    )
  )
})

it("does not offer to import the same active reading twice", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (String(url).includes("/statement-import/") && !options?.method)
      return {
        ...data,
        current_import: {
          source_document_id: "previous",
          account_id: "saved-account",
          filename: "original-statement.pdf",
          evidence_file_id: "file",
          revision: "b".repeat(64),
          transaction_count: 0,
          record_count: 250,
          incomplete_count: 250,
          details: { ...data.metadata, account_number: "00123456789" },
        },
      } as never
    return base(url, options)
  })
  const done = mount()
  await open(false)
  expect(
    screen.getByText("These payments have not reached Transactions")
  ).toBeVisible()
  expect(
    screen.queryByRole("button", { name: "Confirm import of 1 transactions" })
  ).not.toBeInTheDocument()
  expect(
    screen.getByText(/those readings are not payments in Transactions/)
  ).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Review saved incomplete records" })
  )
  expect(done).toHaveBeenCalledTimes(1)
  expect(done).toHaveBeenCalledWith(
    expect.objectContaining({
      case_id: "case",
      account_id: "saved-account",
      source_document_id: "previous",
      record_count: 250,
      incomplete_count: 250,
      filename: "original-statement.pdf",
    })
  )
  expect(
    screen.queryByRole("textbox", { name: "Account number" })
  ).not.toBeInTheDocument()
  expect(sent).toHaveLength(0)
})

it("adds missing statement balances in labelled fields without inventing payments", async () => {
  mount()
  await open()
  fireEvent.click(screen.getByRole("button", { name: "Add opening balance" }))
  fireEvent.change(screen.getByLabelText("Statement opening balance"), {
    target: { value: "0.00" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Add closing balance" }))
  fireEvent.change(screen.getByLabelText("Statement closing balance"), {
    target: { value: "10.00" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: /Confirm import of 1 transactions/ })
  )
  await waitFor(() => expect(sent).toHaveLength(1))
  expect(sent[0]).toMatchObject({
    rows: expect.arrayContaining([
      expect.objectContaining({
        id: "manual:opening-balance",
        excluded: true,
        manual_page: 1,
        balance_minor: "0",
      }),
      expect.objectContaining({
        id: "manual:closing-balance",
        excluded: true,
        manual_page: 1,
        balance_minor: "1000",
      }),
    ]),
  })
})

it("takes a balance-only review directly to its missing balance and saves it to the batch", async () => {
  const { BatchReviewContext } = await import("../lib/batch-review-context")
  const save = vi.fn().mockResolvedValue({ status: "ready" }),
    saved = vi.fn()
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) =>
    url.includes("/statement-import/file?")
      ? ({
          ...data,
          rows: [data.rows[0]],
          transaction_count: 0,
          page_numbers: [1, 2],
        } as never)
      : base(url, options)
  )
  useStatementWorkspace.getState().select("anonymous:case", "file")
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <BatchReviewContext.Provider value={{ save, saved }}>
        <StatementImportPanel caseId="case" onImported={vi.fn()} />
      </BatchReviewContext.Provider>
    </QueryClientProvider>
  )
  await screen.findByText("Review statement.pdf")
  const submit = screen.getByRole("button", { name: "Save statement balances" })
  expect(submit).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Show items to check" }))
  expect(
    screen.getByRole("button", { name: "Add opening balance" })
  ).toHaveFocus()
  fireEvent.click(screen.getByRole("button", { name: "Add opening balance" }))
  const opening = screen.getByLabelText("Statement opening balance")
  await waitFor(() => expect(opening).toHaveFocus())
  fireEvent.change(opening, { target: { value: "1817.77" } })
  fireEvent.change(screen.getByLabelText("opening balance source page"), {
    target: { value: "2" },
  })
  expect(submit).toBeEnabled()
  fireEvent.click(submit)
  await waitFor(() => expect(saved).toHaveBeenCalledOnce())
  expect(save).toHaveBeenCalledWith(
    expect.objectContaining({
      rows: expect.arrayContaining([
        expect.objectContaining({
          id: "manual:opening-balance",
          balance_minor: "181777",
          manual_page: 2,
          excluded: true,
        }),
      ]),
    })
  )
  expect(sent).toHaveLength(0)
})

it("hides an excluded payment and lets the investigator restore it without a reason", async () => {
  mount()
  await open()
  fireEvent.click(screen.getByLabelText("Include row 1:0:1"))
  expect(screen.queryByLabelText("Include row 1:0:1")).not.toBeInTheDocument()
  fireEvent.click(screen.getByLabelText("Show excluded rows"))
  expect(screen.getByLabelText("Include row 1:0:1")).not.toBeChecked()
  fireEvent.click(screen.getByLabelText("Include row 1:0:1"))
  expect(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  ).toBeEnabled()
})

it("saves a statement with matching balances and no payments, with a clear confirmation", async () => {
  const empty = {
    ...data,
    can_import_balances: true,
    transaction_count: 0,
    rows: [
      {
        ...data.rows[0],
        kind: "balance",
        fields: { description: "Opening Balance", balance: "10000" },
      },
      {
        ...data.rows[1],
        kind: "balance",
        excluded: true,
        fields: { description: "Closing Balance", balance: "10000" },
      },
    ],
  }
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (String(url).includes("/confirm?")) {
      sent.push(options?.body)
      return {
        case_id: "case",
        evidence_file_id: "file",
        transaction_count: 0,
        applied: true,
      } as never
    }
    return String(url).includes("statement-import")
      ? (empty as never)
      : base(url, options)
  })
  const done = mount()
  await open()
  const save = screen.getByRole("button", { name: "Save statement balances" })
  expect(save).toBeEnabled()
  fireEvent.click(save)
  await waitFor(() => expect(done).toHaveBeenCalledTimes(1))
  expect(sent[0]).toMatchObject({
    rows: [
      { id: "1:0:0", excluded: true, balance_minor: "10000" },
      { id: "1:0:1", excluded: true, balance_minor: "10000" },
    ],
  })
  expect(
    await screen.findByText(/Statement balances saved/)
  ).toBeInTheDocument()
})
it("records a closure notice with no payments and no invented closing balance", async () => {
  const closure = {
    ...data,
    can_record_account_closure: true,
    transaction_count: 0,
    metadata: {
      ...data.metadata,
      account_closure: {
        date: "2020-06-29",
        page_number: 1,
        table_index: 0,
        row_index: 1,
        source_cells: data.rows[1].source_cells,
      },
    },
    rows: [
      {
        ...data.rows[0],
        kind: "balance",
        fields: { description: "Opening Balance", balance: "0" },
      },
      {
        ...data.rows[1],
        kind: "statement_information",
        excluded: true,
        fields: {
          account_closed_on: "2020-06-29",
          description: "06/29 ID 0011 VISA PAYMENT Closed",
        },
      },
    ],
  }
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (String(url).includes("/confirm?")) {
      sent.push(options?.body)
      return {
        case_id: "case",
        evidence_file_id: "file",
        transaction_count: 0,
        account_closed_on: "2020-06-29",
        applied: true,
      } as never
    }
    return String(url).includes("statement-import")
      ? (closure as never)
      : base(url, options)
  })
  const done = mount()
  await open()
  expect(
    screen.getByText(/An unprinted closing balance remains unknown/)
  ).toBeVisible()
  expect(
    screen.getByRole("button", { name: "View account closure in PDF" })
  ).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Save account closure" }))
  await waitFor(() => expect(done).toHaveBeenCalledTimes(1))
  expect(done).toHaveBeenCalledWith(
    expect.objectContaining({
      transaction_count: 0,
      account_closed_on: "2020-06-29",
    })
  )
  expect(sent[0]).toMatchObject({
    rows: [
      { balance_minor: "0", excluded: true },
      { balance_minor: null, excluded: true },
    ],
  })
})

it("opens a receipt separately from statement periods and returns to the same file choices", async () => {
  const choices = [
    {
      id: "s".repeat(64),
      institution: "Example Bank",
      account_reference: "12345",
      period_start: "2023-01-01",
      period_end: "2023-01-31",
      page_numbers: [1],
    },
    {
      id: receiptFixture.document_id!,
      institution: "Andrews Federal Credit Union",
      account_reference: "XXXX5678",
      account_label: "Deposit receipt",
      document_kind: "deposit_receipt",
      period_start: "",
      period_end: "",
      printed_statement_date: "03/23/21",
      page_numbers: [2],
    },
  ]
  vi.mocked(fetchAPI).mockImplementation(async (url) => {
    if (String(url).startsWith("/api/evidence?"))
      return {
        files: [
          {
            id: "file",
            case_id: "case",
            original_filename: "mixed.pdf",
            status: "processed",
          },
        ],
      } as never
    const selected = String(url).includes(
      "statement_id=" + receiptFixture.document_id
    )
    return {
      ...data,
      rows: [],
      statement_choices: choices,
      statement_id: selected ? receiptFixture.document_id : null,
      ...(selected
        ? { document_review: { ...receiptFixture, evidence_file_id: "file" } }
        : {}),
    } as never
  })
  mount()
  useStatementWorkspace.getState().select("anonymous:case", "file")
  await screen.findByText("Statements and receipts in this PDF")
  fireEvent.click(
    screen.getByRole("button", { name: /Deposit receipt.*pages 2/ })
  )
  await screen.findByRole("region", { name: "Deposit receipt review" })
  expect(screen.queryByRole("button", { name: /Confirm import/ })).toBeNull()
  fireEvent.click(
    screen.getByRole("button", { name: "Choose another statement or receipt" })
  )
  await screen.findByText("Statements and receipts in this PDF")
})

it("allows importing an unchanged flagged reading without an acknowledgement", async () => {
  const flagged = structuredClone(data)
  flagged.rows[1].issues = [
    "Check the inferred date against the printed statement period.",
  ]
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    url.includes("/statement-import/file?")
      ? Promise.resolve(flagged as never)
      : base(url, options)
  )
  const done = mount()
  await open()
  fireEvent.click(
    screen.getByRole("button", { name: "Hide corrections and import choices" })
  )
  const button = screen.getByRole("button", {
    name: "Confirm import of 1 transactions",
  })
  expect(button).toBeEnabled()
  fireEvent.click(button)
  await waitFor(() => expect(done).toHaveBeenCalledTimes(1))
  expect(sent[0]).toMatchObject({
    rows: [
      { id: "1:0:0" },
      {
        id: "1:0:1",
        reason: "",
      },
    ],
  })
})

it("marks a valid flagged row checked without typing a reason and retains that decision on import", async () => {
  const flagged = structuredClone(data)
  flagged.rows[1].issues = [
    "Check the inferred date against the printed statement period.",
  ]
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    url.includes("/statement-import/file?")
      ? Promise.resolve(flagged as never)
      : base(url, options)
  )
  const done = mount()
  await open()
  fireEvent.click(screen.getByRole("button", { name: "Mark checked" }))
  expect(
    screen.queryByRole("button", { name: "Mark checked" })
  ).not.toBeInTheDocument()
  fireEvent.click(
    screen.getByRole("button", { name: "Hide corrections and import choices" })
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  )
  await waitFor(() => expect(done).toHaveBeenCalledTimes(1))
  expect(sent[0]).toMatchObject({
    rows: [
      { id: "1:0:0" },
      { id: "1:0:1", reason: "Checked against the original statement." },
    ],
  })
})

it("links missing account details without blocking import and clears the issue when corrected", async () => {
  mount()
  await open()
  fireEvent.change(screen.getByLabelText("Account holder"), {
    target: { value: "" },
  })
  expect(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  ).toBeEnabled()
  expect(
    screen.getByRole("region", { name: "Statement issues and edits" })
  ).toHaveTextContent("Account holder not identified.")
  fireEvent.click(screen.getAllByRole("button", { name: "Go to field" })[0])
  expect(screen.getByLabelText("Account holder")).toHaveFocus()
  fireEvent.change(screen.getByLabelText("Account holder"), {
    target: { value: "Corrected holder" },
  })
  fireEvent.change(screen.getByLabelText("Reason for detail corrections"), {
    target: { value: "Checked the printed account name." },
  })
  expect(
    screen.queryByRole("region", { name: "Statement issues and edits" })
  ).not.toBeInTheDocument()
  expect(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  ).toBeEnabled()
})

it("offers a new financial reading for an unseparated collection without asking users to correct thousands of text rows", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    url.includes("/statement-import/file?")
      ? Promise.resolve({
          ...data,
          reading_failure:
            "The saved reading has not separated the statement periods. Transaction amounts on later pages may already be readable.",
          rows: [],
          transaction_count: 0,
          page_numbers: [1, 2, 3],
        } as never)
      : base(url, options)
  )
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Import a statement" }))
  await screen.findByRole("option", { name: "statement.pdf" })
  fireEvent.change(screen.getByLabelText("Uploaded statement"), {
    target: { value: "file" },
  })
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "statement periods"
  )
  expect(
    screen.getByRole("button", { name: "Reprocess statement" })
  ).toBeVisible()
  expect(screen.getByLabelText("Reading method")).toHaveValue("automatic")
  expect(screen.getByText("Original PDF beside editable values")).toBeVisible()
  expect(
    screen.queryByRole("button", { name: /Confirm import/ })
  ).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText("Original PDF page"), {
    target: { value: "3" },
  })
  expect(screen.getByLabelText("Original PDF page")).toHaveValue("3")
})

it("moves between transactions and source pages without accepting headings as payments", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) =>
    url.includes("/statement-import/file?")
      ? ({
          ...data,
          page_numbers: [1, 2, 3],
          rows: [
            data.rows[0],
            { ...data.rows[1], page_number: 2 },
            {
              ...data.rows[1],
              id: "3:0:1",
              page_number: 3,
              fields: { ...data.rows[1].fields, description: "Second payment" },
            },
          ],
          transaction_count: 2,
        } as never)
      : base(url, options)
  )
  mount()
  await open()
  expect(screen.getByText("Transaction 1 of 2")).toBeVisible()
  expect(screen.getByLabelText("Statement viewer page")).toHaveValue("2")
  expect(
    screen.getByRole("button", { name: "Previous transaction" })
  ).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Next transaction" }))
  expect(screen.getByLabelText("Statement viewer page")).toHaveValue("3")
  expect(screen.getByText("Transaction 2 of 2")).toBeVisible()
  expect(
    screen.getByRole("button", { name: "Next transaction" })
  ).toBeDisabled()
  fireEvent.keyDown(
    screen.getByRole("group", { name: "Transaction navigation" }),
    { key: "ArrowLeft" }
  )
  expect(screen.getByLabelText("Statement viewer page")).toHaveValue("2")
  expect(sent).toEqual([])
})

it("switches periods directly and restores a correction when returning", async () => {
  useAuthStore.setState({
    user: { id: "reviewer", username: "reviewer" } as never,
  })
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  const choices = ["first", "second"].map((id, index) => ({
    id,
    institution: "Example Bank",
    account_reference: "12345",
    period_start: `2023-0${index + 1}-01`,
    period_end: `2023-0${index + 1}-28`,
    page_numbers: [index + 1],
    checks: { balance_status: "matches", flagged_rows: 0 },
  }))
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (!url.includes("/statement-import/file?")) return base(url, options)
    const id = new URL(url, "http://test").searchParams.get("statement_id")
    return {
      ...data,
      statement_choices: choices,
      statement_id: id,
      revision: (id === "second" ? "b" : "a").repeat(64),
      rows: id ? data.rows : [],
    } as never
  })
  mount()
  useStatementWorkspace.getState().select("reviewer:case", "file")
  fireEvent.change(await screen.findByLabelText("Statement period"), {
    target: { value: "first" },
  })
  await screen.findByText("Review statement.pdf")
  fireEvent.click(screen.getByRole("button", { name: "Edit import values" }))
  fireEvent.change(screen.getByLabelText("Description 1:0:1"), {
    target: { value: "Corrected payment" },
  })
  fireEvent.change(screen.getByLabelText("Reason 1:0:1"), {
    target: { value: "Checked source" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Next period" }))
  await waitFor(() =>
    expect(screen.getByLabelText("Statement period")).toHaveValue("second")
  )
  await screen.findByText("Review statement.pdf")
  fireEvent.click(screen.getByRole("button", { name: "Previous period" }))
  await screen.findByText("Review statement.pdf")
  fireEvent.click(screen.getByRole("button", { name: "Edit import values" }))
  expect(screen.getByLabelText("Description 1:0:1")).toHaveValue(
    "Corrected payment"
  )
  expect(screen.getByLabelText("Reason 1:0:1")).toHaveValue("Checked source")
  expect(sent).toEqual([])
})

it("shows a clean statement ready for a single confirmation without opening corrections", async () => {
  vi.mocked(useStatementChecks).mockReturnValue({
    admission: {
      can_import: true,
      status: "reconciled",
      revision: "c".repeat(64),
      blockers: [],
    },
    checks: [
      {
        kind: "closing_balance",
        status: "matches",
        expected_minor: "12500",
        printed_minor: "12500",
        difference_minor: "0",
      },
    ],
    pending: false,
    error: undefined,
    revision: "c".repeat(64),
    retry: vi.fn(),
  })
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  const balances = ["Opening", "Closing"].map((role, index) => ({
    ...data.rows[0],
    id: `balance-${index}`,
    kind: "balance",
    fields: { description: `${role} Balance`, balance: index ? "12500" : "0" },
  }))
  vi.mocked(fetchAPI).mockImplementation(async (url, options) =>
    url.includes("/statement-import/file?")
      ? ({ ...data, rows: [...balances, ...data.rows] } as never)
      : base(url, options)
  )
  const done = mount()
  useStatementWorkspace.getState().select("anonymous:case", "file")
  expect(
    await screen.findByRole("region", { name: "Statement checks" })
  ).toHaveTextContent("Ready to confirm")
  expect(
    screen.getByRole("region", { name: "Statement checks" })
  ).toHaveTextContent("Opening and closing balance: matches")
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  )
  await waitFor(() => expect(done).toHaveBeenCalledTimes(1))
})

it("restores a server-saved bulk review, focuses its row and saves without importing", async () => {
  const { BatchReviewContext } = await import("../lib/batch-review-context")
  const save = vi.fn().mockResolvedValue({ status: "ready" }),
    saved = vi.fn()
  const user = useAuthStore.getState().user
  const owner = user?.id || user?.username || "anonymous"
  useStatementWorkspace.getState().select(`${owner}:case`, "file")
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <BatchReviewContext.Provider
        value={{
          rowId: "1:0:1",
          save,
          saved,
          draft: {
            revision: data.revision,
            holder: "Checked owner",
            account: "12345",
            institution: "Example Bank",
            periodStart: "2023-01-01",
            periodEnd: "2023-01-31",
            detailsReason: "Checked account",
            amountText: {},
            rows: [
              {
                id: "1:0:1",
                excluded: false,
                date: "2023-01-02",
                description: "Corrected description",
                counterparty: "Example payer",
                amount_minor: "12500",
                direction: "credit",
                balance_minor: "12500",
                reason: "Checked payment",
              },
            ],
          },
        }}
      >
        <StatementImportPanel caseId="case" onImported={vi.fn()} />
      </BatchReviewContext.Provider>
    </QueryClientProvider>
  )
  expect(await screen.findByLabelText("Description 1:0:1")).toHaveValue(
    "Corrected description"
  )
  expect(screen.queryByLabelText("Uploaded statement")).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Save for bulk import" }))
  await waitFor(() => expect(saved).toHaveBeenCalled())
  expect(save).toHaveBeenCalledWith(
    expect.objectContaining({
      holder: "Checked owner",
      rows: expect.arrayContaining([
        expect.objectContaining({
          description: "Corrected description",
          reason: "Checked payment",
        }),
      ]),
    })
  )
  expect(sent).toHaveLength(0)
})

it("holds a printed difference even after an explanation is saved", async () => {
  vi.mocked(useStatementChecks).mockReturnValue({
    admission: {
      can_import: false,
      status: "needs_review",
      revision: "c".repeat(64),
      blockers: [
        {
          message: "Payments do not add up to the closing balance.",
          row_id: null,
        },
      ],
    },
    checks: [
      {
        kind: "closing_balance",
        status: "difference",
        expected_minor: "12500",
        printed_minor: "12600",
        difference_minor: "-100",
      },
    ],
    pending: false,
    error: undefined,
    revision: "c".repeat(64),
    retry: vi.fn(),
  })
  const done = mount()
  await open()
  const confirm = screen.getByRole("button", {
    name: "Confirm import of 1 transactions",
  })
  expect(confirm).toBeDisabled()
  fireEvent.click(
    screen.getByLabelText("I checked these differences against the PDF")
  )
  fireEvent.change(screen.getByLabelText("Why the difference remains"), {
    target: { value: "Investigate the printed discrepancy." },
  })
  expect(confirm).toBeDisabled()
  expect(done).not.toHaveBeenCalled()
  expect(screen.getByRole("button", { name: "Save progress" })).toBeEnabled()
})
it("holds import while checks are pending or fail without blocking corrections", async () => {
  const state = {
    checks: [],
    admission: undefined,
    pending: true,
    error: undefined as string | undefined,
    revision: undefined,
    retry: vi.fn(),
  }
  vi.mocked(useStatementChecks).mockReturnValue(state)
  mount()
  await open()
  const confirm = screen.getByRole("button", {
    name: "Confirm import of 1 transactions",
  })
  expect(confirm).toBeDisabled()
  state.pending = false
  state.error = "Connection interrupted"
  fireEvent.change(screen.getByLabelText("Description 1:0:1"), {
    target: { value: "Changed" },
  })
  expect(confirm).toBeDisabled()
  expect(
    screen.getByRole("button", { name: "Retry statement checks" })
  ).toBeInTheDocument()
  expect(screen.getByLabelText("Description 1:0:1")).toHaveValue("Changed")
})

it("edits beside a printed row, preserves its source text and uses the correction for import", async () => {
  const done = mount()
  useStatementWorkspace.getState().select("anonymous:case", "file")
  fireEvent.click(await screen.findByRole("button", { name: "Edit this row" }))
  expect(
    screen.getByRole("region", { name: "Edit selected statement row" })
  ).toBeVisible()
  fireEvent.change(screen.getByLabelText("Corrected transaction date"), {
    target: { value: "2023-01-03" },
  })
  fireEvent.change(screen.getByLabelText("Reason for this row correction"), {
    target: { value: "Checked the printed day." },
  })
  expect(screen.getByRole("button", { name: "2023-01-02" })).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Done editing this row" }))
  expect(
    screen.queryByRole("region", { name: "Edit selected statement row" })
  ).toBeNull()
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  )
  await waitFor(() => expect(done).toHaveBeenCalledTimes(1))
  expect((sent[0] as { rows: unknown[] }).rows).toContainEqual(
    expect.objectContaining({
      id: "1:0:1",
      date: "2023-01-03",
      reason: "Checked the printed day.",
    })
  )
})

it.each([false, true])(
  "holds matching statements (%s) while keeping partial-overlap comparison optional",
  async (matching) => {
    vi.mocked(useStatementCoverageReview).mockReturnValue({
      data: {
        available: true,
        matching_statement: matching,
        revision: "d".repeat(64),
        candidates: [
          {
            file_id: "other-file",
            filename: "Other statement.pdf",
            statement_id: null,
            source_document_id: "other-source",
            status: "imported",
            period_start: "2023-01-01",
            period_end: "2023-01-31",
          },
        ],
      },
      pending: false,
      error: undefined,
      retry: vi.fn(),
    })
    mount()
    await open()
    const confirm = screen.getByRole<HTMLButtonElement>("button", {
      name: "Confirm import of 1 transactions",
    })
    expect(confirm.disabled).toBe(matching)
    expect(screen.getByText("Other statement.pdf")).toBeVisible()
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "I have compared these files and need to import this statement too",
      })
    )
    expect(confirm.disabled).toBe(matching)
    fireEvent.change(
      screen.getByLabelText("Reason for importing overlapping statements"),
      { target: { value: "Additional records in this statement." } }
    )
    expect(confirm).toBeEnabled()
    fireEvent.click(confirm)
    await waitFor(() => expect(sent).toHaveLength(1))
    expect(sent[0]).toMatchObject({
      coverage_review_reason: "Additional records in this statement.",
      coverage_review_revision: "d".repeat(64),
    })
  }
)

it("keeps labels beside correction inputs and imports routine changes without reasons", async () => {
  mount()
  await open()
  const region = screen.getByRole("region", {
    name: "Statement correction columns",
  })
  for (const [field, label] of [
    ["date", "Transaction date"],
    ["description", "Description"],
    ["credit", "Credit EUR"],
    ["debit", "Debit EUR"],
    ["balance", "Printed balance EUR"],
  ]) {
    expect(
      region.querySelector(`label[for="review-${field}-1:0:1"]`)
    ).toHaveTextContent(label)
  }
  fireEvent.change(screen.getByLabelText("Credit 1:0:1"), {
    target: { value: "126.50" },
  })
  fireEvent.change(screen.getByLabelText("Account holder"), {
    target: { value: "Corrected holder" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  )
  await waitFor(() => expect(sent).toHaveLength(1))
  expect(sent[0]).toMatchObject({
    holder: "Corrected holder",
    details_reason: "",
    rows: [{}, { amount_minor: "12650", reason: "" }],
  })
})

it("saves a single zero closing balance without asking for an opening balance or payment", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  const balance = {
    ...data,
    can_import_balances: true,
    transaction_count: 0,
    rows: [
      {
        ...data.rows[0],
        kind: "balance",
        fields: { description: "Closing Balance", balance: "0" },
      },
    ],
  }
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    url.includes("statement-import") && !url.includes("/confirm?")
      ? Promise.resolve(balance as never)
      : base(url, options)
  )
  mount()
  await open()
  fireEvent.click(
    screen.getByRole("button", { name: "Save statement balances" })
  )
  await waitFor(() => expect(sent).toHaveLength(1))
  expect(sent[0]).toMatchObject({
    rows: [{ excluded: true, balance_minor: "0" }],
  })
})
