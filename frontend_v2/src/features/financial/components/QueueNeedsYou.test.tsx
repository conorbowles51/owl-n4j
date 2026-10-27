import { fireEvent, render, screen, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { ReviewQueuePanel } from "./ReviewQueuePanel"

vi.mock("@/lib/api-client", async (actual) => ({
  ...(await actual<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true, canUpload: true }),
}))

const proposal = { currency: { value: "EUR", label: "same account's 4 saved statements, all EUR", confirmed: false } }
const entry = (n: number, over: Record<string, unknown> = {}) => ({
  id: `i${n}`, batch_id: "b1", file_id: `f${n}`, file_ids: [`f${n}`], source_id: `f${n}`, statement_id: `s${n}`,
  filename: `Month ${n}.pdf`, holder: "Holder", account: "0001", institution: "Bank", currency: "",
  period_start: `2021-0${n}-01`, period_end: `2021-0${n}-28`, page: 1, can_import: false, status: "attention",
  bucket: "waiting", file_position: 1, file_statements: 1, other_problems: 0, problem_total: 1,
  issue: "Currency not printed: EUR proposed", issue_reason: "currency", reasons: ["currency"], proposals: proposal,
  ...over,
})
const counts = { imported: 3, saving: 0, waiting: 4, ready: 1, filled: 0, copies: 2, unreadable: 0, unreadable_files: 0,
  rechecking: 5, left_unimported: 0, assigned: 0, unexplained: 0 }
const items = [
  entry(1),
  entry(2),
  entry(3),
  entry(4, { issue_reason: "reading", reasons: ["reading"], proposals: undefined, currency: "EUR",
    issue: "A manually added transaction needs a page from this PDF.",
    issue_messages: ["A manually added transaction needs a page from this PDF."],
    worked_by: { user_id: "u2", name: "Sam Diaz" } }),
]
const listed = (n: number) => ({
  key: `draft:f${n}:s${n}`, file_id: `f${n}`, source_id: null, statement_id: `s${n}`, revision: "a".repeat(64),
  filename: `Month ${n}.pdf`, status: "Not imported",
  values: { holder: "Holder", account_number: "0001", institution: "Bank", currency: "" },
})
let sent: { url: string; body: Record<string, unknown> }[] = []
beforeEach(() => {
  sent = []
  useAuthStore.setState({ user: { id: "u1", username: "maria", name: "Maria Lopez", role: null } })
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url: string, options?: { body?: unknown }) => {
    sent.push({ url, body: options?.body as Record<string, unknown> })
    if (url.includes("/review/queue"))
      return { case_id: "case", file_ids: [], counts, status_line: "", items, ready: [], copies: [], unreadable: [],
        unreadable_files: [], rechecking: [] } as never
    if (url.includes("/account-details/statements"))
      return { case_id: "case", items: [1, 2, 3].map(listed), notices: [] } as never
    if (url.includes("/account-details/preview"))
      return { case_id: "case", preview_revision: "p".repeat(64), updated: 3,
        items: [1, 2, 3].map((n) => ({ ...listed(n), changes: { currency: { before: "", after: "EUR" } } })) } as never
    if (url.includes("/account-details/save"))
      return { case_id: "case", updated: 3, unchanged: 0, imported: 0, drafts: 3 } as never
    throw Error(`unexpected ${url}`)
  })
})
afterEach(() => useAuthStore.setState({ user: null }))

const mount = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/cases/case/financial?view=statements&queue=1"]}>
        <ReviewQueuePanel caseId="case" onOpenBatch={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>
  )

it("names the signed-in investigator, keeps what Loupe handles apart, and answers one account's statements with one confirm", async () => {
  mount()
  expect(await screen.findByRole("tab", { name: /Needs Maria \(4\)/ })).toHaveAttribute("aria-selected", "true")
  expect(screen.getByRole("tab", { name: /Not waiting on you \(8\)/ })).toHaveAttribute("aria-selected", "false")
  expect(screen.getByRole("heading", { name: "Needs Maria" })).toBeVisible()
  const list = screen.getByRole("list", { name: "Statements to review" })
  // Three statements of one account, one proposal: one item, not three rows.
  const group = within(list).getByRole("listitem", { name: "Same answer for several statements" })
  expect(group).toHaveTextContent("one answer for 3 statements")
  expect(within(group).getByLabelText("What is wrong")).toHaveTextContent(
    "3 statements of Bank account 0001: confirm the currency is EUR"
  )
  // Work a colleague saved names that colleague, with what to do and where.
  expect(screen.getByText("Needs Sam")).toBeVisible()
  expect(screen.getByText("A row Sam added needs its page")).toBeVisible()
  expect(screen.getByRole("button", { name: "Choose the page" })).toBeVisible()
  fireEvent.click(within(group).getByRole("button", { name: "Confirm EUR for 3" }))
  expect(await screen.findByLabelText("Result of the shared fix")).toBeVisible()
  const preview = sent.find((call) => call.url.includes("/account-details/preview"))!
  expect(preview.body).toMatchObject({ changes: { currency: "EUR" }, mode: "replace" })
  expect((preview.body.targets as unknown[]).length).toBe(3)
  expect(sent.some((call) => call.url.includes("/account-details/save"))).toBe(true)
})
