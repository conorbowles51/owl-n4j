import { fireEvent, render, screen, within } from "@testing-library/react"
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

const quiet = (n: number) => ({
  id: `q${n}`, batch_id: "b1", file_id: `f${n}`, file_ids: [`f${n}`], source_id: `f${n}`, statement_id: null,
  filename: `Quiet ${n}.pdf`, holder: "Ana", account: "1", institution: "Bank", currency: "USD",
  period_start: `2021-0${n}-01`, period_end: `2021-0${n}-28`, can_import: false, status: "attention",
  bucket: "waiting", file_position: 1, file_statements: 1, other_problems: 0, problem_total: 1,
  issue: "No payments read: check every page, then confirm", issue_reason: "no_activity",
})
const counts = { imported: 0, saving: 0, waiting: 3, ready: 0, copies: 0, unreadable: 0, unreadable_files: 0,
  rechecking: 0, left_unimported: 0, assigned: 0, unexplained: 0 }
let saved = false
const queue = () => ({
  case_id: "case", file_ids: [], counts, status_line: "", copies: [], unreadable: [], unreadable_files: [],
  rechecking: [],
  items: saved ? [quiet(3)] : [1, 2, 3].map(quiet),
  ready: saved ? [1, 2].map((n) => ({ ...quiet(n), bucket: "ready" })) : [],
})
const row = (n: number) => ({
  key: `draft:f${n}:`, file_id: `f${n}`, source_id: null, statement_id: null, revision: "a".repeat(64),
  filename: `Quiet ${n}.pdf`, status: "Not imported", values: {},
})
const calls: { url: string; body: { targets?: { file_id: string }[]; changes?: unknown } }[] = []
beforeEach(() => {
  saved = false
  calls.length = 0
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url: string, options?: { body?: unknown }) => {
    const body = (options?.body ?? {}) as (typeof calls)[number]["body"]
    calls.push({ url, body })
    if (url.includes("/review/queue")) return queue() as never
    if (url.includes("/account-details/statements"))
      return { case_id: "case", items: [1, 2, 3].map(row), notices: [] } as never
    if (url.includes("/account-details/preview"))
      return {
        case_id: "case", preview_revision: "p".repeat(64), updated: 2,
        items: body.targets!.map((t) => {
          const n = Number(t.file_id.slice(1))
          return n === 3
            ? { ...row(n), changes: {}, excluded_reason: "Its printed opening and ending balances differ, so money moved in this period." }
            : { ...row(n), changes: { no_activity_confirmed: { before: "Not confirmed", after: "Confirmed" } } }
        }),
      } as never
    if (url.includes("/account-details/save")) {
      saved = true
      return { case_id: "case", updated: 2, unchanged: 0, imported: 0, drafts: 2 } as never
    }
    throw Error(`unexpected ${url}`)
  })
})

it("selects every 'no payments read' statement, says how many will be confirmed, then confirms them together", async () => {
  // Only one kind of issue is waiting: the shared fix shows without choosing a filter.
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/cases/case/financial?view=statements&queue=1"]}>
        <ReviewQueuePanel caseId="case" onOpenBatch={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>
  )
  const box = await screen.findByRole("region", { name: "Confirm no payments together" })
  expect(within(box).getByLabelText("Statements chosen to confirm")).toHaveTextContent("0 of 3 selected")
  fireEvent.click(within(box).getByRole("button", { name: "Select all 3" }))
  expect(within(box).getByLabelText("Statements chosen to confirm")).toHaveTextContent("3 of 3 selected")
  // Each row can be unticked on its own.
  expect(screen.getByLabelText("Choose Quiet 2.pdf (2021-02-01 to 2021-02-28) to confirm no payments")).toBeChecked()
  const check = within(box).getByRole("button", { name: "Check which of the 3 can be confirmed" })
  expect(check).toBeDisabled()
  fireEvent.click(within(box).getByRole("checkbox"))
  fireEvent.click(check)
  const plan = await within(box).findByLabelText("What will be confirmed")
  expect(plan).toHaveTextContent(
    "2 of 3 selected statements will be confirmed with no payments. 1 cannot be: 1 its printed opening and ending balances differ"
  )
  // Nothing is saved before the count is confirmed.
  expect(calls.some((call) => call.url.includes("/save"))).toBe(false)
  fireEvent.click(within(box).getByRole("button", { name: "Confirm no payments for 2 statements" }))
  expect(await screen.findByLabelText("Result of the shared fix")).toHaveTextContent(
    "2 statements confirmed with no payments. 1 of 3 still need something; they stay listed below with what is left. 2 ready to import."
  )
  const preview = calls.find((call) => call.url.includes("/preview"))!
  expect(preview.body.changes).toEqual({ no_activity_confirmed: true })
  expect(preview.body.targets).toHaveLength(3)
})
