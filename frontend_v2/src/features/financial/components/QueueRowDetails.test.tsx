import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"
import { ApiError, fetchAPI } from "@/lib/api-client"
import { ReviewQueuePanel } from "./ReviewQueuePanel"

vi.mock("@/lib/api-client", async (actual) => ({
  ...(await actual<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true, canUpload: true }),
}))

const entry = {
  id: "i1", batch_id: "b1", file_id: "f1", file_ids: ["f1"], source_id: "f1", statement_id: "s".repeat(64),
  filename: "Savings.pdf", holder: "Ana Ruiz", account: "1234", institution: "", currency: "",
  period_start: "2021-01-01", period_end: "2021-01-31", can_import: false, status: "attention", bucket: "waiting",
  file_position: 1, file_statements: 2, other_problems: 0, problem_total: 1,
  issue: "Currency not printed: choose one", issue_reason: "currency",
  proposals: { currency: { value: "MXN", label: "same account's 3 saved statements, all MXN", confirmed: false } },
}
const counts = { imported: 0, saving: 0, waiting: 1, ready: 0, copies: 0, unreadable: 0, unreadable_files: 0,
  rechecking: 0, left_unimported: 0, assigned: 0, unexplained: 0 }
let fixed = false
const queue = () => ({
  case_id: "case", file_ids: [], counts: fixed ? { ...counts, waiting: 0, ready: 1 } : counts, status_line: "",
  items: fixed ? [] : [entry], ready: fixed ? [{ ...entry, bucket: "ready", currency: "MXN" }] : [],
  copies: [], unreadable: [], unreadable_files: [], rechecking: [],
})
const listed = (statement_id: string) => ({
  key: `draft:f1:${statement_id}`, file_id: "f1", source_id: null, statement_id, revision: "a".repeat(64),
  filename: "Savings.pdf", status: "Not imported",
  values: { holder: "Ana Ruiz", account_number: "1234", institution: "", currency: "" },
})
let sent: { url: string; body: Record<string, unknown> }[] = []
beforeEach(() => {
  fixed = false
  sent = []
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url: string, options?: { body?: unknown }) => {
    sent.push({ url, body: options?.body as Record<string, unknown> })
    if (url.includes("/review/queue")) return queue() as never
    if (url.includes("/account-details/statements"))
      return { case_id: "case", items: [listed("t".repeat(64)), listed("s".repeat(64))], notices: [] } as never
    if (url.includes("/account-details/preview")) {
      const body = options!.body as { changes: Record<string, string> }
      return {
        case_id: "case", preview_revision: "p".repeat(64), updated: 1,
        items: [{ ...listed("s".repeat(64)), changes: Object.fromEntries(
          Object.entries(body.changes).map(([k, v]) => [k, { before: "", after: v }])) }],
      } as never
    }
    if (url.includes("/account-details/save")) {
      fixed = true
      return { case_id: "case", updated: 1, unchanged: 0, imported: 0, drafts: 1 } as never
    }
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

it("fixes currency, bank and holder on the row itself, beside the shared fix, and says where it stands", async () => {
  mount()
  const row = await screen.findByRole("group", { name: "Details of Savings.pdf" })
  // The proposed currency is already chosen; the bank is typed in; nothing pops up.
  expect(within(row).getByLabelText("Currency for Savings.pdf")).toHaveValue("MXN")
  fireEvent.change(within(row).getByLabelText("Bank for Savings.pdf"), { target: { value: "Banorte" } })
  fireEvent.click(within(row).getByRole("button", { name: "Save currency, bank" }))
  expect(await screen.findByLabelText("Result of your last save")).toHaveTextContent(
    "Savings.pdf (2021-01-01 to 2021-01-31): Saved. Ready to import"
  )
  expect(screen.queryByRole("dialog")).toBeNull()
  // The second statement of the file was the one changed, with only the changed fields.
  const previewCall = sent.find((call) => call.url.includes("/preview"))!
  expect(previewCall.body).toMatchObject({
    targets: [{ file_id: "f1", statement_id: "s".repeat(64), revision: "a".repeat(64) }],
    changes: { currency: "MXN", institution: "Banorte" },
    mode: "replace",
  })
  const save = sent.find((call) => call.url.includes("/save"))!
  expect(save.body).toMatchObject({ preview_revision: "p".repeat(64), request_id: previewCall.body.request_id })
})

it("keeps the shared fix alongside the row fix", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/cases/case/financial?view=statements&queue=1&queueIssue=currency"]}>
        <ReviewQueuePanel caseId="case" onOpenBatch={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>
  )
  expect(await screen.findByRole("button", { name: "Fix all 1 together" })).toBeVisible()
  expect(screen.getByRole("group", { name: "Details of Savings.pdf" })).toBeVisible()
})

it("says plainly when the row could not be saved and keeps the typed values", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.includes("/review/queue")) return queue() as never
    if (url.includes("/account-details/statements"))
      return { case_id: "case", items: [listed("s".repeat(64))], notices: [] } as never
    if (url.includes("/account-details/preview")) throw new ApiError("The batch is still checking files.", 422)
    throw Error(`unexpected ${url}`)
  })
  mount()
  const row = await screen.findByRole("group", { name: "Details of Savings.pdf" })
  fireEvent.change(within(row).getByLabelText("Bank for Savings.pdf"), { target: { value: "Banorte" } })
  fireEvent.click(within(row).getByRole("button", { name: "Save currency, bank" }))
  await waitFor(() =>
    expect(within(row).getByRole("alert")).toHaveTextContent(
      "The batch is still checking files. Nothing was changed; your values are kept."
    )
  )
  expect(within(row).getByLabelText("Bank for Savings.pdf")).toHaveValue("Banorte")
})
