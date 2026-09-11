import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { StatementImportPanel } from "./StatementImportPanel"
import { fetchAPI } from "@/lib/api-client"
import { useStatementWorkspace } from "../stores/statement-workspace"
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
      issues: [],
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
      issues: [],
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
