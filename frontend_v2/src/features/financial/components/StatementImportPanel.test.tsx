import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { StatementImportPanel } from "./StatementImportPanel"
import { fetchAPI } from "@/lib/api-client"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: () => (
    <div>Original PDF beside editable values</div>
  ),
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
    screen.getByRole("button", { name: "Show corrections and import choices" })
  )
}
beforeEach(() => {
  useAuthStore.setState({ user: null })
  sessionStorage.clear()
  useStatementWorkspace.setState({ selections: {}, reviewChoices: {} })
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
  ).toBeDisabled()
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

it("leaves an unknown credit or debit blank and requires the investigator to choose", async () => {
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
  fireEvent.change(screen.getByLabelText("Reason 1:0:1"), {
    target: { value: "Checked the original payment marker" },
  })
  const confirm = screen.getByRole("button", {
    name: "Confirm import of 1 transactions",
  })
  expect(confirm).toBeDisabled()
  fireEvent.change(screen.getByLabelText("Credit 1:0:1"), {
    target: { value: "125.00" },
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
  expect(saved.rows[1]).toMatchObject({
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
  ).toBeDisabled()
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

it("does not offer to import the same active reading twice", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (String(url).includes("/statement-import/") && !options?.method)
      return {
        ...data,
        current_import: {
          source_document_id: "previous",
          evidence_file_id: "file",
          revision: "b".repeat(64),
          transaction_count: 1,
        },
      } as never
    return base(url, options)
  })
  const done = mount()
  await open()
  expect(
    screen.getByText("This statement has already been imported")
  ).toBeVisible()
  expect(
    screen.getByRole("button", { name: "Confirm import of 1 transactions" })
  ).toBeDisabled()
  fireEvent.click(
    screen.getByRole("button", { name: "Open imported transactions" })
  )
  expect(done).toHaveBeenCalledTimes(1)
  expect(sent).toHaveLength(0)
})

it("keeps a newly excluded payment visible so its required reason can be entered", async () => {
  mount()
  await open()
  fireEvent.click(screen.getByLabelText("Include row 1:0:1"))
  expect(screen.getByLabelText("Include row 1:0:1")).not.toBeChecked()
  expect(screen.getByLabelText("Reason 1:0:1")).toBeVisible()
  fireEvent.change(screen.getByLabelText("Reason 1:0:1"), {
    target: { value: "Pending missing date evidence" },
  })
  expect(screen.getByLabelText("Reason 1:0:1")).toHaveValue(
    "Pending missing date evidence"
  )
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
