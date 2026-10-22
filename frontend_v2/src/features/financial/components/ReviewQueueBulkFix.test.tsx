import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { ReviewQueuePanel } from "./ReviewQueuePanel"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true, canUpload: true }),
}))

const base = {
  source_id: "f1", holder: "", account: "", institution: "", currency: "", can_import: false,
  status: "attention", bucket: "waiting", other_problems: 0, problem_total: 1, file_position: 1,
  file_statements: 1, period_start: "2021-01-01", period_end: "2021-01-31",
  issue: "Currency not printed: choose one", issue_reason: "currency",
}
const entry = (n: number) => ({
  ...base, id: `i${n}`, batch_id: "b1", file_id: `f${n}`, file_ids: [`f${n}`], statement_id: null,
  filename: `Statement ${n}.pdf`,
})
const queueOf = (n: number) => ({
  case_id: "case", file_ids: [],
  counts: { imported: 0, saving: 0, waiting: n, ready: 0, copies: 0, unreadable: 0, unreadable_files: 0,
    rechecking: 0, left_unimported: 0, assigned: 0, unexplained: 0 },
  status_line: "", items: Array.from({ length: n }, (_, i) => entry(i + 1)),
  copies: [], unreadable: [], unreadable_files: [], rechecking: [], ready: [],
})
const row = (n: number) => ({
  key: `draft:f${n}:`, file_id: `f${n}`, source_id: null, statement_id: null, revision: "a".repeat(64),
  filename: `Statement ${n}.pdf`, status: "Not imported",
  values: { holder: "", account_number: "", institution: "", currency: "", period_start: "", period_end: "" },
})

let waiting = 2
beforeEach(() => {
  waiting = 2
  useFinancialDraftStore.setState({ drafts: {} })
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.includes("/review/queue")) return queueOf(waiting) as never
    if (url.includes("/account-details/statements"))
      return { case_id: "case", items: [1, 2, 3].map(row), notices: [] } as never
    throw Error(`unexpected ${url}`)
  })
})

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/cases/case/financial?view=statements&queue=1&queueIssue=currency"]}>
        <ReviewQueuePanel caseId="case" onOpenBatch={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>
  )
  return client
}

it("keeps the shared fix open, with its selection, while the queue refreshes underneath it", async () => {
  const client = mount()
  fireEvent.click(await screen.findByRole("button", { name: "Fix all 2 together" }))
  expect(await screen.findByText("Edit account details for statements")).toBeVisible()
  fireEvent.click(await screen.findByRole("button", { name: "Select all 2 matching statements" }))
  expect(screen.getByText("2 selected")).toBeVisible()
  // Another statement joins the list while she works (files are still being read).
  waiting = 3
  await act(async () => {
    await client.invalidateQueries({ queryKey: ["financial-review-queue"] })
  })
  await waitFor(() => expect(screen.getByRole("button", { name: /Fix all 3 together/, hidden: true })).toBeVisible())
  // The dialog she was working in is still open with what she selected.
  expect(screen.getByText("Edit account details for statements")).toBeVisible()
  expect(screen.getByText("2 selected")).toBeVisible()
})

it("says when fewer statements can be listed than the queue chose, instead of dropping them", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.includes("/review/queue")) return queueOf(2) as never
    if (url.includes("/account-details/statements"))
      return { case_id: "case", items: [row(1)], notices: [] } as never
    throw Error(`unexpected ${url}`)
  })
  mount()
  fireEvent.click(await screen.findByRole("button", { name: "Fix all 2 together" }))
  expect(await screen.findByText(/Listed 1 of the 2 statements chosen in the queue/)).toBeVisible()
})

it("still says what the shared fix did when it leaves nothing listed", async () => {
  const sent: string[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url: string, options?: unknown) => {
    sent.push(url)
    if (url.includes("/review/queue")) return queueOf(waiting) as never
    if (url.includes("/account-details/statements"))
      return { case_id: "case", items: [1, 2].map(row), notices: [] } as never
    const body = (options as { body: { targets: { file_id: string }[]; changes: Record<string, string> } }).body
    if (url.includes("/account-details/preview"))
      return {
        case_id: "case", preview_revision: "b".repeat(64), updated: body.targets.length,
        items: body.targets.map((t) => ({
          ...row(Number(t.file_id.slice(1))), after: body.changes,
          changes: { currency: { before: "", after: "EUR" } },
        })),
      } as never
    if (url.includes("/account-details/save")) {
      waiting = 0
      return { case_id: "case", updated: 2, unchanged: 0, imported: 0, drafts: 2, items: [], account_changes: [] } as never
    }
    throw Error(`unexpected ${url}`)
  })
  mount()
  fireEvent.click(await screen.findByRole("button", { name: "Fix all 2 together" }))
  fireEvent.click(await screen.findByRole("button", { name: "Select all 2 matching statements" }))
  fireEvent.change(screen.getByLabelText("New currency"), { target: { value: "EUR" } })
  fireEvent.click(screen.getByRole("button", { name: "Review changes for 2 statements" }))
  fireEvent.click(await screen.findByRole("button", { name: "Save changes to 2 statements" }))
  expect(await screen.findByLabelText("Result of the shared fix")).toHaveTextContent(
    "Saved. None of the 2 statements need anything more for this."
  )
})
