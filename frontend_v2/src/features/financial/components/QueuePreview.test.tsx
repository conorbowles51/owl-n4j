import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { ReviewQueuePanel } from "./ReviewQueuePanel"

vi.mock("@/lib/api-client", async (actual) => ({
  ...(await actual<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true, canUpload: true }),
}))
// The page render itself is the statement review's; here it says what it was asked to draw.
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: (props: { sourceDocumentId?: string; locatorPayload: unknown; wholePage?: boolean }) => (
    <div data-testid="page">
      {JSON.stringify({ file: props.sourceDocumentId, locator: props.locatorPayload, whole: !!props.wholePage })}
    </div>
  ),
}))

const entry = (n: number, over: Record<string, unknown> = {}) => ({
  id: `i${n}`, batch_id: "b1", file_id: `f${n}`, file_ids: [`f${n}`], source_id: `f${n}`, statement_id: `s${n}`,
  filename: `Month ${n}.pdf`, holder: "Holder", account: "0001", institution: "Bank", currency: "USD",
  period_start: `2021-0${n}-01`, period_end: `2021-0${n}-28`, page: 1, can_import: false, status: "attention",
  bucket: "waiting", file_position: 1, file_statements: 1, other_problems: 0, problem_total: 1,
  issue: "Closing balance off by 1.00 USD", issue_reason: "balance", reasons: ["balance"],
  opening_minor: "100", closing_minor: "200", transaction_count: 3, ...over,
})
const items = [
  entry(1, { page: 2 }),
  entry(2, { row_id: "7:0:17", page: 7, issue_pages: [7], issue: "3 rows unreadable on page 7", issue_reason: "reading", reasons: ["reading"] }),
  entry(3, { account: "", period_start: "", period_end: "" }),
]
const counts = { imported: 0, saving: 0, waiting: 3, ready: 0, filled: 0, copies: 0, unreadable: 0, unreadable_files: 0,
  rechecking: 0, left_unimported: 0, assigned: 0, unexplained: 0 }
// The statement's reading, as the statement review loads it: the problem row has measured cells on page 7.
const reading = {
  case_id: "case", evidence_file_id: "f2", filename: "Month 2.pdf", currency: "USD", revision: "a".repeat(64),
  metadata: { holder: "Holder", account_number: "0001", institution: "Bank", period: "February 2021",
    period_start: "2021-02-01", period_end: "2021-02-28" },
  rows: [{
    id: "7:0:17", page_number: 7, table_index: 0, row_index: 17,
    source_cells: [{ column_index: 0, expected_text: "02/03", locator: { kind: "page_rectangle", page: 7,
      rect: [100, 200, 900, 240], page_size: [1000, 2000], units: "millipoints", space: "pdf_displayed" } }],
    fields: { date: "2021-02-03", description: "Unreadable", amount_minor: "", direction: "debit" },
    issues: ["Amount unreadable"], excluded: false, kind: "transaction",
  }],
  issues: [], transaction_count: 3, needs_attention: 1, page_numbers: [1, 7],
}
beforeEach(() => {
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.includes("/review/queue"))
      return { case_id: "case", file_ids: [], counts, status_line: "", items, ready: [], copies: [], unreadable: [],
        unreadable_files: [], rechecking: [] } as never
    if (url.includes("/statement-import/f2?")) return reading as never
    throw Error(`unexpected ${url}`)
  })
})

const mount = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/cases/case/financial?view=statements&queue=1"]}>
        <ReviewQueuePanel caseId="case" onOpenBatch={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>
  )
const drawn = () => JSON.parse(screen.getByTestId("page").textContent!)
const key = (target: Element | Window, k: string) => act(() => { fireEvent.keyDown(target, { key: k }) })

it("previews the page with the problem highlighted beside the item's fields, and moves with J/K and the arrows", async () => {
  mount()
  const list = await screen.findByRole("list", { name: "Statements to review" })
  const previews = within(list).getAllByRole("button", { name: "Preview" })
  expect(previews).toHaveLength(3)
  previews[0].focus()
  fireEvent.click(previews[0])
  const panel = screen.getByRole("dialog", { name: "Preview of Month 1.pdf" })
  // No problem row: the whole page the item names, as the statement review opens it.
  expect(drawn()).toEqual({ file: "f1", locator: { kind: "page_only", page: 2 }, whole: true })
  expect(within(panel).getByText("1 of 3", { exact: false })).toBeVisible()
  expect(within(panel).getByRole("button", { name: "Open page 2" })).toBeVisible()

  key(window, "j")
  expect(screen.getByRole("dialog", { name: "Preview of Month 2.pdf" })).toBeVisible()
  // A problem row: its measured cells on its page, the statement review's row highlight.
  await waitFor(() => expect(drawn().locator.kind).toBe("page_rectangle"))
  expect(drawn()).toMatchObject({ file: "f2", locator: { kind: "page_rectangle", page: 7 }, whole: false })

  key(window, "ArrowDown")
  const third = screen.getByRole("dialog", { name: "Preview of Month 3.pdf" })
  // The item's own fields, editable here: the account number and dates it lacks.
  const account = within(third).getByLabelText("Account number for Month 3.pdf")
  expect(within(third).getByLabelText("Statement start date for Month 3.pdf")).toBeVisible()
  expect(within(third).getByLabelText("Before it can be imported")).toHaveTextContent("account number Required")
  // Typing in a field: J, K and Esc belong to the field.
  account.focus()
  key(account, "j")
  key(account, "Escape")
  expect(screen.getByRole("dialog", { name: "Preview of Month 3.pdf" })).toBeVisible()

  key(window, "k")
  expect(screen.getByRole("dialog", { name: "Preview of Month 2.pdf" })).toBeVisible()
  key(window, "ArrowUp")
  expect(screen.getByRole("dialog", { name: "Preview of Month 1.pdf" })).toBeVisible()
  key(window, "j")
  key(window, "Escape")
  expect(screen.queryByRole("dialog")).toBeNull()
  // Focus returns to the item shown last.
  await waitFor(() => expect(document.activeElement).toHaveAttribute("data-queue-preview", "i2"))
})

it("opens the preview from the file name", async () => {
  mount()
  const list = await screen.findByRole("list", { name: "Statements to review" })
  fireEvent.click(within(list).getByRole("button", { name: "Month 3.pdf" }))
  expect(screen.getByRole("dialog", { name: "Preview of Month 3.pdf" })).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Close preview" }))
  expect(screen.queryByRole("dialog")).toBeNull()
})
