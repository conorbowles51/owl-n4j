import { fireEvent, render, screen, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, useLocation } from "react-router-dom"
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

// OPDMD66 STATEMENTS 5630.pdf statement 2: held for her duplicate decision; its original is imported.
const sentence = "Possible copy of Dec 2023 (5630) (2).pdf, which is already imported: compare the two, then decide"
const copy = {
  id: "i2", batch_id: "b1", file_id: "f1", file_ids: ["f1"], source_id: "f1", statement_id: "s2",
  filename: "STATEMENTS 5630.pdf", holder: "BEE THRIFTY CAMP SPRINGS LLC", account: "1000270585630",
  institution: "Truist Bank", currency: "USD", period_start: "2023-12-01", period_end: "2023-12-29", page: 5,
  can_import: false, status: "attention", bucket: "waiting", file_position: 2, file_statements: 6, other_problems: 0,
  problem_total: 1, issue: sentence, issue_reason: "duplicate", reasons: ["duplicate"], also: [], issue_pages: [],
  issue_messages: [sentence], copy_of: "Dec 2023 (5630) (2).pdf",
  original: { filename: "Dec 2023 (5630) (2).pdf", file_id: "f9", statement_id: "s9", period_start: "2023-12-01",
    period_end: "2023-12-29", page: 1, imported: true, same_file: false, others: 0 },
}
const counts = { imported: 32, saving: 0, waiting: 1, ready: 0, filled: 0, copies: 0, unreadable: 0, unreadable_files: 0,
  rechecking: 0, left_unimported: 0, assigned: 0, unexplained: 0 }

beforeEach(() => {
  useAuthStore.setState({ user: { id: "u1", username: "maria", name: "Maria Lopez", role: null } })
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.includes("/review/queue"))
      return { case_id: "case", file_ids: [], counts, status_line: "", items: [copy], ready: [], copies: [],
        unreadable: [], unreadable_files: [], rechecking: [] } as never
    return {} as never
  })
})
afterEach(() => useAuthStore.setState({ user: null }))

function Where() {
  return <output aria-label="where">{useLocation().search}</output>
}

it("lists an undecided possible copy under Needs you, names its original, and Compare opens the statement to compare", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/cases/case/financial?view=statements&queue=1"]}>
        <ReviewQueuePanel caseId="case" onOpenBatch={vi.fn()} />
        <Where />
      </MemoryRouter>
    </QueryClientProvider>
  )
  expect(await screen.findByRole("tab", { name: /Needs you \(1\)/ })).toHaveAttribute("aria-selected", "true")
  expect(screen.getByRole("heading", { name: /32 of 33 statements are done/ })).toHaveTextContent("1 need your eyes.")
  const list = screen.getByRole("list", { name: "Statements to review" })
  const original = within(list).getByLabelText("Original")
  expect(original).toHaveTextContent("May be a copy of: Dec 2023 (5630) (2).pdf, 2023-12-01 to 2023-12-29: already imported")
  expect(within(list).queryByText(/set aside on purpose|Finished/)).toBeNull()
  fireEvent.click(within(original).getByRole("button", { name: "Compare" }))
  const search = new URLSearchParams(screen.getByLabelText("where").textContent ?? "")
  expect(search.get("queueItem")).toBe("i2")
  expect(search.get("queueCompare")).toBe("i2")
})
