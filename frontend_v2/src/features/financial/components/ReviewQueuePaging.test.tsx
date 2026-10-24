import { fireEvent, render, screen, waitFor } from "@testing-library/react"
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

const entry = (n: number, reason = n % 2 ? "currency" : "reading") => ({
  id: `i${n}`, batch_id: "b1", file_id: `f${n}`, file_ids: [`f${n}`], source_id: `f${n}`, statement_id: null,
  filename: `S${n}.pdf`, holder: "A", account: `${n}`, institution: "B", currency: "USD",
  period_start: "2021-01-01", period_end: "2021-01-31", can_import: false, status: "attention", bucket: "waiting",
  file_position: 1, file_statements: 1, other_problems: 0, problem_total: 1, issue: `Issue ${n}`, issue_reason: reason,
})
const counts = { imported: 5, saving: 0, waiting: 250, ready: 2, copies: 0, unreadable: 0, unreadable_files: 0,
  rechecking: 0, left_unimported: 0, assigned: 0, unexplained: 0 }
// The server's paged answer: one page of the asked list, whole-case counts.
function answer(url: string) {
  const search = new URL(url, "http://x").searchParams
  const limit = search.get("limit")
  const all = Array.from({ length: 250 }, (_, i) => entry(i + 1))
  if (limit === null)
    return { case_id: "case", file_ids: [], counts, status_line: "", items: all, ready: [entry(900), entry(901)],
      copies: [], unreadable: [], unreadable_files: [], rechecking: [] }
  const issue = search.get("issue")
  const offset = Number(search.get("offset"))
  const matching = issue ? all.filter((e) => e.issue_reason === issue) : all
  const page = matching.slice(offset, offset + Number(limit))
  return {
    case_id: "case", file_ids: [], counts, status_line: "", items: page, ready: [], copies: [], unreadable: [],
    unreadable_files: [], rechecking: [],
    totals: { waiting: 250, ready: 2, filled: 0, reader_fix: 0, rechecking: 0, copies: 0, unreadable: 0 },
    page: { list: "waiting", issue, offset, limit: Number(limit), returned: page.length, total: matching.length },
    issue_counts: { currency: 125, reading: 125 },
    ready_item_ids: ["i900", "i901"], refreshing: offset === 0 && !issue,
  }
}
const urls = () => vi.mocked(fetchAPI).mock.calls.map(([url]) => String(url))
beforeEach(() => {
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.includes("/review/queue")) return answer(url) as never
    if (url.includes("/review/save?"))
      return { request_id: "q", queued: 2, held: [], operations: [{ batch_id: "b1", operation_id: "o1", queued: 2 }] } as never
    if (url.includes("/review/save-result"))
      return { case_id: "case", found: 1, pending: 0, imported: 2, already_present: 0, duplicate_ignored: 0,
               failed: [], transaction_count: 3 } as never
    throw Error(`unexpected ${url}`)
  })
})
const mount = (path = "/cases/case/financial?view=statements&queue=1") =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <ReviewQueuePanel caseId="case" onOpenBatch={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>
  )

it("reads one page of the list, says how much there is, and pages on", async () => {
  mount()
  const list = await screen.findByRole("list", { name: "Statements to review" })
  expect(list.children).toHaveLength(50)
  expect(urls()[0]).toContain("limit=50&offset=0&page_list=waiting")
  expect(screen.getByLabelText("Shown of this list")).toHaveTextContent("Showing 1–50 of 250")
  // Counts come from the whole case, never from the page.
  expect(screen.getByLabelText("Statement status")).toHaveTextContent("Waiting for you 250")
  expect(screen.getByRole("button", { name: "All issues (250)" })).toBeVisible()
  expect(screen.getByText(/Updating the numbers/)).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Next 50" }))
  await waitFor(() => expect(screen.getByLabelText("Shown of this list")).toHaveTextContent("Showing 51–100 of 250"))
  expect(urls().some((url) => url.includes("offset=50"))).toBe(true)
  expect(screen.getByText("S51.pdf")).toBeVisible()
})

it("filters by issue on the server, and a shared fix covers every statement of that issue, not the page", async () => {
  mount("/cases/case/financial?view=statements&queue=1&queueIssue=currency")
  expect(await screen.findByLabelText("Shown of this list")).toHaveTextContent("Showing 1–50 of 125")
  expect(urls().some((url) => url.includes("issue=currency") && url.includes("limit=50&"))).toBe(true)
  expect(await screen.findByRole("button", { name: "Fix all 125 together" })).toBeVisible()
  expect(urls().some((url) => url.includes("issue=currency") && url.includes("limit=5000"))).toBe(true)
})

it("imports every ready statement, not only the ones on the page", async () => {
  mount()
  fireEvent.click(await screen.findByRole("button", { name: "Import 2 ready statements" }))
  expect(await screen.findByLabelText("Result of importing ready statements")).toHaveTextContent("2 imported")
  const save = vi.mocked(fetchAPI).mock.calls.find(([url]) => String(url).includes("/review/save?"))!
  expect((save[1] as { body: { item_ids: string[] } }).body.item_ids).toEqual(["i900", "i901"])
})
