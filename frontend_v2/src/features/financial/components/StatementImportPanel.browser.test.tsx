import "@/styles/globals.css"
import "../financial-workspace.css"
import { page } from "vitest/browser"
import { MemoryRouter } from "react-router-dom"
import { StatementFilesPanel } from "./StatementFilesPanel"
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
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { StatementImportPanel } from "./StatementImportPanel"
import { fetchAPI } from "@/lib/api-client"
import { useStatementChecks } from "../hooks/use-statement-checks"
vi.mock("../hooks/use-statement-checks", async (original) => ({
  ...(await original<typeof import("../hooks/use-statement-checks")>()),
  useStatementChecks: vi.fn(),
}))
import { useStatementWorkspace } from "../stores/statement-workspace"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: vi.fn(() => (
    <div className="h-[600px] rounded border bg-white p-8 text-slate-700">
      Synthetic source placeholder. This test checks the correction controls,
      not PDF extraction.
    </div>
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
async function open() {
  fireEvent.click(screen.getByRole("button", { name: "Import a statement" }))
  await screen.findByRole("option", { name: "statement.pdf" })
  fireEvent.change(screen.getByLabelText("Uploaded statement"), {
    target: { value: "file" },
  })
  await screen.findByText("Review statement.pdf")
  fireEvent.click(
    screen.getByText("Show corrections and import choices", {
      selector: "button",
    })
  )
}
beforeEach(() => {
  vi.mocked(useStatementCoverageReview).mockReturnValue({
    data: { available: true, candidates: [], revision: "d".repeat(64) },
    pending: false,
    error: undefined,
    retry: vi.fn(),
  })
  vi.mocked(useStatementChecks).mockReturnValue({
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
    if (url.startsWith("/api/evidence-upload-")) return [] as never
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

it("imports from the review summary without opening corrections or resolving every issue", async () => {
  const originalRead = vi.mocked(fetchAPI).getMockImplementation()!
  const prepared = {
    ...data,
    rows: [
      ...Array.from({ length: 40 }, (_, i) => ({
        ...data.rows[1],
        id: `ready:${i}`,
        row_index: i,
      })),
      ...Array.from({ length: 3 }, (_, i) => ({
        ...data.rows[1],
        id: `incomplete:${i}`,
        row_index: i + 40,
        fields: { ...data.rows[1].fields, amount_minor: "" },
        issues: ["The amount could not be read."],
      })),
    ],
    transaction_count: 43,
    page_numbers: [1],
    statement_page_numbers: [1],
  }
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.startsWith("/api/evidence-upload-")) return [] as never
    if (url.includes("/confirm?")) {
      sent.push(options?.body)
      return {
        case_id: "case",
        evidence_file_id: "file",
        applied: true,
        transaction_count: 40,
        record_count: 43,
        incomplete_count: 3,
      } as never
    }
    return url.includes("statement-import")
      ? (prepared as never)
      : originalRead(url, options)
  })
  await page.viewport(1440, 1000)
  document.documentElement.classList.remove("dark")
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Import a statement" }))
  await screen.findByRole("option", { name: "statement.pdf" })
  fireEvent.change(screen.getByLabelText("Uploaded statement"), {
    target: { value: "file" },
  })
  const summary = await screen.findByRole("region", {
    name: "Statement checks",
  })
  expect(summary).toHaveTextContent(
    "43 records selected · 3 with missing or invalid fields"
  )
  expect(screen.getByLabelText("Credit ready:0")).not.toBeVisible()
  const importNow = screen.getByRole("button", {
    name: /Import .* payments and view Transactions/,
  })
  importNow.scrollIntoView({ block: "center" })
  await page.screenshot({
    path: "/tmp/statement-review-direct-import-light.png",
  })
  fireEvent.click(importNow)
  await waitFor(() => expect(sent).toHaveLength(1))
  const request = sent[0] as {
    rows: {
      id: string
      amount_minor: string
      excluded: boolean
      reason: string
    }[]
  }
  expect(request.rows).toHaveLength(43)
  expect(request.rows.every((row) => !row.excluded && !row.reason)).toBe(true)
  expect(request.rows.filter((row) => row.amount_minor === "")).toHaveLength(3)
})

it("sends all 588 selected PDFs to one preparation request even when a search hides most files", async () => {
  const files = Array.from({ length: 588 }, (_, i) => ({
    id: `pdf-${i}`,
    case_id: "case",
    original_filename: `Statement ${String(i + 1).padStart(3, "0")}.pdf`,
    status: "processed",
  }))
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.startsWith("/api/evidence-upload-")) return [] as never
    if (options?.method === "POST") {
      sent.push(options.body)
      return { id: "prepared-batch", case_id: "case" } as never
    }
    return (
      url.startsWith("/api/evidence?")
        ? { files }
        : { case_id: "case", files: [], truncated: false }
    ) as never
  })
  await page.viewport(1440, 1000)
  render(
    <MemoryRouter>
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
        <StatementFilesPanel caseId="case" register />
      </QueryClientProvider>
    </MemoryRouter>
  )
  fireEvent.click(
    await screen.findByRole("button", { name: "Select all 588 shown files" })
  )
  fireEvent.change(screen.getByLabelText("Search statement files"), {
    target: { value: "Statement 588" },
  })
  expect(
    screen.getByText("588 files selected · 587 hidden by filters")
  ).toBeVisible()
  expect(screen.getByLabelText("Select Statement 588.pdf")).toBeChecked()
  await page.screenshot({
    path: "/tmp/statement-files-bulk-preparation-light.png",
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare statements from 588 files" })
  )
  await waitFor(() => expect(sent).toHaveLength(1))
  expect(sent[0]).toMatchObject({
    file_ids: files.map((file) => file.id),
    folder_ids: [],
  })
})

it("keeps field labels visible after scrolling through correction rows in light mode", async () => {
  document.documentElement.classList.remove("dark")
  await page.viewport(1440, 1000)
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  const many = {
    ...data,
    rows: [
      data.rows[0],
      ...Array.from({ length: 40 }, (_, i) => ({
        ...data.rows[1],
        id: `row:${i}`,
        row_index: i + 1,
        fields: {
          ...data.rows[1].fields,
          description: `Example payment ${i + 1}`,
        },
      })),
    ],
  }
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    url.includes("statement-import") && !url.includes("/confirm?")
      ? Promise.resolve(many as never)
      : base(url, options)
  )
  mount()
  await open()
  const amount = screen.getByLabelText("Credit row:30")
  amount.scrollIntoView({ block: "center", inline: "center" })
  await waitFor(() => {
    const rect = document
      .querySelector('label[for="review-credit-row:30"]')!
      .getBoundingClientRect()
    expect(rect.top).toBeGreaterThan(0)
    expect(rect.bottom).toBeLessThan(window.innerHeight)
    expect(rect.left).toBeGreaterThanOrEqual(0)
    expect(rect.right).toBeLessThanOrEqual(window.innerWidth)
  })
  await page.screenshot({
    path: "/tmp/statement-review-labelled-fields-light.png",
  })
  fireEvent.change(amount, { target: { value: "127.00" } })
  const confirm = screen.getByRole("button", {
    name: "Confirm import of 40 transactions",
  })
  expect(confirm).toBeEnabled()
  fireEvent.click(confirm)
  await waitFor(() => expect(sent).toHaveLength(1))
  expect(
    (
      sent[0] as {
        rows: { id: string; amount_minor: string; reason: string }[]
      }
    ).rows.find((r) => r.id === "row:30")
  ).toMatchObject({ amount_minor: "12700", reason: "" })
})

it("pages 1200 correction rows, restores a late edit and submits every row", async () => {
  useAuthStore.setState({
    user: { id: "reviewer", username: "reviewer" } as never,
  })
  const originalRead = vi.mocked(fetchAPI).getMockImplementation()!
  const large = {
    ...data,
    transaction_count: 1200,
    rows: Array.from({ length: 1200 }, (_, i) => ({
      ...data.rows[1],
      id: `payment-${i}`,
      page_number: Math.floor(i / 25) + 1,
      fields: { ...data.rows[1].fields, description: `Payment ${i}` },
      source_cells: [],
    })),
  }
  vi.mocked(fetchAPI).mockImplementation(async (url, options) =>
    String(url).includes("/statement-import/") &&
    !String(url).includes("/confirm?")
      ? (large as never)
      : originalRead(url, options)
  )
  mount()
  await open()
  expect(screen.getAllByLabelText(/^Include row/)).toHaveLength(50)
  fireEvent.change(screen.getByLabelText("Review page"), {
    target: { value: "23" },
  })
  fireEvent.change(screen.getByLabelText("Description payment-1199"), {
    target: { value: "Corrected last payment" },
  })
  fireEvent.change(screen.getByLabelText("Reason payment-1199"), {
    target: { value: "Checked original" },
  })
  fireEvent(window, new Event("pagehide"))
  const saved = JSON.parse(
    sessionStorage.getItem(
      `loupe-statement-review:reviewer:case:file:${data.revision}`
    )!
  )
  expect(saved.row_mode).toBe("changes")
  expect(saved.rows).toHaveLength(1)
  fireEvent.click(screen.getByRole("button", { name: "Previous review rows" }))
  fireEvent.click(screen.getByRole("button", { name: "Next review rows" }))
  expect(screen.getByLabelText("Description payment-1199")).toHaveValue(
    "Corrected last payment"
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm import of 1200 transactions" })
  )
  await waitFor(() => expect(sent).toHaveLength(1))
  const request = sent[0] as { rows: { description: string }[] }
  expect(request.rows).toHaveLength(1200)
  expect(request.rows[1199].description).toBe("Corrected last payment")
})

it("sets aside empty entries across all pages, preserves partial readings and edits, and supports undo", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  const emptyRows = Array.from({ length: 61 }, (_, i) => ({
    ...data.rows[0],
    id: `empty:${i}`,
    row_index: i + 2,
    kind: "unresolved",
    excluded: false,
    fields: {},
    issues: ["Text did not match transaction columns."],
    source_cells: [
      { column_index: 0, expected_text: `Original line ${i}`, locator: {} },
    ],
  }))
  const partial = {
    ...emptyRows[0],
    id: "partial",
    fields: { description: "Readable merchant" },
  }
  const many = { ...data, rows: [...data.rows, ...emptyRows, partial] }
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    url.includes("statement-import") && !url.includes("/confirm?")
      ? Promise.resolve(many as never)
      : base(url, options)
  )
  mount()
  await open()
  expect(screen.getAllByText("Original line 0")[0]).toBeVisible()
  // Once the investigator supplies any value, it is no longer an empty entry.
  fireEvent.change(screen.getByLabelText("Description empty:0"), {
    target: { value: "My recovered payment" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Exclude 60 blank rows from import" })
  )
  expect(
    screen.getByRole("button", { name: "Confirm import of 3 transactions" })
  ).toBeEnabled()
  expect(
    screen.queryByLabelText("Include row empty:60")
  ).not.toBeInTheDocument()
  expect(screen.getByLabelText("Description empty:0")).toHaveValue(
    "My recovered payment"
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Undo excluding blank rows" })
  )
  expect(
    screen.getByRole("button", { name: "Exclude 60 blank rows from import" })
  ).toBeEnabled()
  fireEvent.click(
    screen.getByRole("button", { name: "Exclude 60 blank rows from import" })
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm import of 3 transactions" })
  )
  await waitFor(() => expect(sent).toHaveLength(1))
  const request = sent[0] as {
    rows: { id: string; excluded: boolean; reason: string }[]
  }
  expect(request.rows).toHaveLength(64)
  expect(request.rows.filter((r) => !r.excluded).map((r) => r.id)).toEqual([
    "1:0:1",
    "empty:0",
    "partial",
  ])
  expect(request.rows.find((r) => r.id === "empty:60")).toMatchObject({
    excluded: true,
    reason: "",
  })
})

it("keeps a 51-period PDF manageable from file list through saved-period review and removal preview", async () => {
  const { StatementRegister } = await import("./StatementRegister")
  await page.viewport(1280, 900)
  const owner =
    useAuthStore.getState().user?.id ||
    useAuthStore.getState().user?.username ||
    "anonymous"
  useStatementWorkspace.getState().setReviewChoice(`${owner}:case:file`, {
    statementId: "period-2",
    currency: "",
  })
  const choices = Array.from({ length: 51 }, (_, i) => ({
    id: `period-${i + 1}`,
    institution: "Example Bank",
    account_reference: "12345",
    period_start: `2023-${String((i % 12) + 1).padStart(2, "0")}-01`,
    period_end: `2023-${String((i % 12) + 1).padStart(2, "0")}-28`,
    page_numbers: [i + 1],
  }))
  const periods = choices.map((choice, i) => ({
    id: choice.id,
    account_id: "account",
    account_label: "Example Ltd · 12345",
    start: choice.period_start,
    end: choice.period_end,
    source_status: "admitted",
    index: i,
  }))
  const writes: string[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.startsWith("/api/evidence-upload-")) return [] as never
    if (options?.method === "POST") writes.push(url)
    if (url.startsWith("/api/evidence?"))
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
    if (url.includes("statement-import/files?"))
      return {
        case_id: "case",
        truncated: false,
        files: [
          { evidence_file_id: "file", current_transactions: 653, periods },
        ],
      } as never
    if (url.includes("/removals/preview"))
      return {
        case_id: "case",
        revision: "f".repeat(64),
        file_count: 1,
        reading_count: 1,
        transaction_count: 653,
        incomplete_count: 0,
        statement_count: 51,
        batch_count: 1,
        archived_batch_count: 1,
        updated_batch_count: 0,
        files: [{ id: "file", filename: "statement.pdf" }],
        can_remove: true,
      } as never
    if (url.includes("statement-import/file?"))
      return {
        ...data,
        statement_id: "period-2",
        statement_choices: choices,
        current_import: {
          source_document_id: "document",
          evidence_file_id: "file",
          revision: "e".repeat(64),
          transaction_count: 6,
          currency: "EUR",
        },
      } as never
    return data as never
  })
  render(
    <MemoryRouter>
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <StatementRegister caseId="case">
          <StatementImportPanel caseId="case" onImported={vi.fn()} />
        </StatementRegister>
      </QueryClientProvider>
    </MemoryRouter>
  )
  const review = await screen.findByRole("button", {
    name: "Review statement.pdf",
  })
  const remove = screen.getByRole("button", {
    name: "Remove from Financial: statement.pdf",
  })
  expect(
    screen.getByText(
      "49 more periods in this PDF. Open the file to choose a period."
    )
  ).toBeVisible()
  expect(remove.getBoundingClientRect().bottom).toBeLessThan(window.innerHeight)
  fireEvent.click(review)
  const context = await screen.findByRole("region", {
    name: "Current statement context",
  })
  expect(context).toHaveTextContent("This PDF contains 51 account statements")
  expect(context).toHaveTextContent(
    "Already imported: 6 payments from this period"
  )
  const payments = within(context).getByRole("button", {
    name: "View 6 payments in Transactions for this period",
  })
  expect(payments).toBeVisible()
  expect(payments.getBoundingClientRect().bottom).toBeLessThan(
    window.innerHeight
  )
  fireEvent.click(screen.getByRole("button", { name: "All files & imports" }))
  expect(
    screen.getByRole("button", { name: "Review statement.pdf" })
  ).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Select all 1 shown file" })
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Review removal of 1 selected file" })
  )
  expect(
    await screen.findByRole("dialog", { name: "Remove financial imports?" })
  ).toBeVisible()
  expect(
    await screen.findByText(/51 statement periods · 653 transactions/)
  ).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  expect(writes).toHaveLength(1)
  expect(writes[0]).toContain("/removals/preview")
})
