import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { ApiError, fetchAPI } from "@/lib/api-client"
import type { StatementDuplicateDisposition } from "../lib/statement-duplicate"
import {
  StatementDuplicateDecision,
  type StatementDuplicateDecisionProps,
} from "./StatementDuplicateDecision"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("@/components/ui/document-viewer", () => ({
  DocumentViewer: ({
    documentName,
    initialPage,
    onOpenChange,
  }: {
    documentName: string
    initialPage: number
    onOpenChange: (open: boolean) => void
  }) => (
    <div role="dialog" aria-label={documentName}>
      Source page {initialPage}
      <button onClick={() => onOpenChange(false)}>Close original</button>
    </div>
  ),
}))

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})
const caseId = "10000000-0000-4000-8000-000000000001"
const fileId = "10000000-0000-4000-8000-000000000002"
const retainedId = "10000000-0000-4000-8000-000000000003"
const readingRevision = "a".repeat(64)
const statementId = "b".repeat(64)
const ignored: StatementDuplicateDisposition = {
  policy: "pending-statement-duplicate-v1",
  reading_revision: readingRevision,
  revision: "c".repeat(64),
  status: "ignored",
  label: "Duplicate - Ignored by system",
  reason:
    "The full statement identity and financial reading match the retained source.",
  current: true,
  matched_fields: [
    "bank",
    "full_account_number",
    "account_holder",
    "period_start",
    "period_end",
    "currency",
    "account_type",
  ],
  basis: "identical_financial_reading",
  retained: {
    evidence_file_id: retainedId,
    statement_id: "d".repeat(64),
    source_document_id: null,
    filename: "Synthetic retained statement.pdf",
    page_number: 5,
  },
}
const response = (decision = ignored) => ({
  case_id: caseId,
  evidence_file_id: fileId,
  statement_id: statementId,
  duplicate_disposition: decision,
})
function mount(changes: Partial<StatementDuplicateDecisionProps> = {}) {
  const onDecision = vi.fn()
  const onOpenRetained = vi.fn()
  const props: StatementDuplicateDecisionProps = {
    caseId,
    fileId,
    statementId,
    currency: "USD",
    readingRevision,
    decision: null,
    canEdit: true,
    onDecision,
    onOpenRetained,
    ...changes,
  }
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const element = (updated: StatementDuplicateDecisionProps) => (
    <QueryClientProvider client={client}>
      <StatementDuplicateDecision {...updated} />
    </QueryClientProvider>
  )
  const view = render(element(props))
  return {
    onDecision,
    onOpenRetained,
    unmount: view.unmount,
    rerender: (updated: Partial<StatementDuplicateDecisionProps>) =>
      view.rerender(element({ ...props, ...updated })),
  }
}

it("checks only on request, saves the scoped decision and exposes the retained source and review", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(response())
  const { onDecision, onOpenRetained } = mount()
  expect(fetchAPI).not.toHaveBeenCalled()
  fireEvent.click(
    screen.getByRole("button", { name: "Check duplicate status" })
  )
  expect(
    await screen.findByRole("heading", {
      name: "Duplicate - Ignored by system",
    })
  ).toBeVisible()
  expect(fetchAPI).toHaveBeenCalledTimes(1)
  expect(fetchAPI).toHaveBeenCalledWith(
    `/api/financial/statement-import/${fileId}/duplicate-disposition?case_id=${caseId}`,
    {
      method: "POST",
      body: {
        action: "check",
        expected_reading_revision: readingRevision,
        statement_id: statementId,
        currency: "USD",
      },
    }
  )
  expect(onDecision).toHaveBeenCalledWith(ignored)
  expect(
    screen.getByText(/Matching details: Bank, Full account number/)
  ).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Open retained original" })
  )
  expect(
    screen.getByRole("dialog", { name: "Synthetic retained statement.pdf" })
  ).toHaveTextContent("Source page 5")
  fireEvent.click(screen.getByRole("button", { name: "Close original" }))
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  fireEvent.click(
    screen.getByRole("button", { name: "Open retained statement review" })
  )
  expect(onOpenRetained).toHaveBeenCalledWith(ignored.retained)
})

it("restores an ignored copy for comparison without claiming an import or readiness", async () => {
  const restored = {
    ...ignored,
    revision: "e".repeat(64),
    status: "restored" as const,
    label: "Restored for review",
    reason: "Investigate a possible revised statement.",
  }
  vi.mocked(fetchAPI).mockResolvedValue(response(restored))
  const onBusy = vi.fn()
  const { onDecision } = mount({ decision: ignored, canCheck: false, onBusy })
  fireEvent.change(
    screen.getByLabelText("Reason for restoring to review (optional)"),
    { target: { value: restored.reason } }
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Restore for comparison" })
  )
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Restored for comparison. No transactions were imported."
  )
  expect(
    screen.getByRole("heading", { name: "Restored for review" })
  ).toBeVisible()
  expect(
    screen.getByText(/does not add transactions or mark it ready/)
  ).toBeVisible()
  expect(
    screen.getByRole("button", { name: "Open retained original" })
  ).toBeVisible()
  expect(onDecision).toHaveBeenCalledWith(restored)
  expect(fetchAPI).toHaveBeenCalledWith(expect.any(String), {
    method: "POST",
    body: {
      action: "restore",
      expected_reading_revision: readingRevision,
      expected_decision_revision: ignored.revision,
      statement_id: statementId,
      currency: "USD",
      reason: restored.reason,
    },
  })
  expect(fetchAPI).toHaveBeenCalledTimes(1)
  expect(onBusy.mock.calls).toEqual([[true], [false]])
})

it("explains why checking is disabled and waits for saved changes before posting", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(response())
  const onBusy = vi.fn()
  const { rerender } = mount({
    canCheck: false,
    checkDisabledReason: "Use Save progress to save these corrections first.",
    onBusy,
  })
  const check = screen.getByRole("button", { name: "Check duplicate status" })
  expect(check).toBeDisabled()
  expect(check).toHaveAccessibleDescription(
    "Use Save progress to save these corrections first."
  )
  fireEvent.click(check)
  expect(fetchAPI).not.toHaveBeenCalled()
  expect(onBusy).not.toHaveBeenCalled()
  rerender({ canCheck: true })
  expect(check).toBeEnabled()
  fireEvent.click(check)
  expect(await screen.findByRole("status")).toHaveTextContent("Duplicate check saved.")
  expect(onBusy.mock.calls).toEqual([[true], [false]])
})

it("keeps the parent busy until a pending check fails, then permits recovery", async () => {
  let reject!: (reason: Error) => void
  vi.mocked(fetchAPI).mockImplementation(
    () => new Promise((_resolve, fail) => { reject = fail })
  )
  const onBusy = vi.fn()
  mount({ onBusy })
  fireEvent.click(screen.getByRole("button", { name: "Check duplicate status" }))
  await waitFor(() => expect(fetchAPI).toHaveBeenCalledTimes(1))
  expect(onBusy.mock.calls).toEqual([[true]])
  const pending = screen.getByRole("button", { name: "Checking duplicates…" })
  expect(pending).toBeDisabled()
  fireEvent.click(pending)
  expect(fetchAPI).toHaveBeenCalledTimes(1)
  reject(new Error("Network interrupted"))
  expect(await screen.findByRole("alert")).toHaveTextContent("The result could not be confirmed.")
  expect(onBusy.mock.calls).toEqual([[true], [false]])
  expect(screen.getByRole("button", { name: "Check duplicate status" })).toBeEnabled()
})

it("releases busy state on unmount without applying or releasing the late result again", async () => {
  let finish!: (value: unknown) => void
  vi.mocked(fetchAPI).mockImplementation(
    () => new Promise((resolve) => { finish = resolve })
  )
  const onBusy = vi.fn()
  const { unmount, onDecision } = mount({ onBusy })
  fireEvent.click(screen.getByRole("button", { name: "Check duplicate status" }))
  await waitFor(() => expect(fetchAPI).toHaveBeenCalledTimes(1))
  expect(onBusy.mock.calls).toEqual([[true]])
  unmount()
  expect(onBusy.mock.calls).toEqual([[true], [false]])
  finish(response())
  await vi.waitFor(() => expect(vi.mocked(fetchAPI).mock.results[0].value).resolves.toEqual(response()))
  expect(onBusy.mock.calls).toEqual([[true], [false]])
  expect(onDecision).not.toHaveBeenCalled()
})

it("keeps the ignored source and typed reason when a stale decision is refused, then resets on reopen", async () => {
  vi.mocked(fetchAPI).mockRejectedValue(
    new ApiError(
      "The duplicate decision changed. Reopen this statement before restoring it.",
      409
    )
  )
  const { onDecision, rerender } = mount({ decision: ignored })
  fireEvent.change(
    screen.getByLabelText("Reason for restoring to review (optional)"),
    { target: { value: "Compare the added page" } }
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Restore for comparison" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "The duplicate decision changed"
  )
  expect(
    screen.getByRole("button", { name: "Restore for comparison" })
  ).toBeDisabled()
  expect(
    screen.getByLabelText("Reason for restoring to review (optional)")
  ).toHaveValue("Compare the added page")
  expect(screen.getByText("Synthetic retained statement.pdf")).toBeVisible()
  expect(onDecision).not.toHaveBeenCalled()
  const newer = { ...ignored, revision: "f".repeat(64) }
  rerender({ decision: newer })
  expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  expect(
    screen.getByRole("button", { name: "Restore for comparison" })
  ).toBeEnabled()
  expect(fetchAPI).toHaveBeenCalledTimes(1)
})

it("shows stale decisions as needing comparison and permits source inspection without editing access", () => {
  mount({
    decision: { ...ignored, current: false, status: "needs_comparison" },
    canEdit: false,
  })
  expect(
    screen.getByRole("heading", { name: "Compare this statement" })
  ).toBeVisible()
  expect(
    screen.queryByRole("button", { name: "Restore for comparison" })
  ).not.toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "Check duplicate status" })
  ).not.toBeInTheDocument()
  fireEvent.click(
    screen.getByRole("button", { name: "Open retained original" })
  )
  expect(screen.getByRole("dialog")).toBeVisible()
  expect(fetchAPI).not.toHaveBeenCalled()
})

it.each([
  { case_id: retainedId },
  { evidence_file_id: retainedId },
  { statement_id: "e".repeat(64) },
  { duplicate_disposition: { ...ignored, reading_revision: "e".repeat(64) } },
])(
  "refuses a response from a different case, file, period or reading %j",
  async (change) => {
    vi.mocked(fetchAPI).mockResolvedValue({ ...response(), ...change })
    const { onDecision } = mount()
    fireEvent.click(
      screen.getByRole("button", { name: "Check duplicate status" })
    )
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "could not be verified for this statement"
    )
    expect(onDecision).not.toHaveBeenCalled()
    expect(
      screen.queryByRole("heading", { name: "Duplicate - Ignored by system" })
    ).not.toBeInTheDocument()
  }
)

it("does not apply a late response after the investigator opens another statement", async () => {
  let finish!: (value: unknown) => void
  vi.mocked(fetchAPI).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  const { onDecision, rerender } = mount()
  fireEvent.click(
    screen.getByRole("button", { name: "Check duplicate status" })
  )
  await waitFor(() => expect(fetchAPI).toHaveBeenCalledTimes(1))
  rerender({ statementId: "f".repeat(64) })
  finish(response())
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Check duplicate status" })
    ).toBeEnabled()
  )
  expect(onDecision).not.toHaveBeenCalled()
  expect(
    screen.queryByRole("heading", { name: "Duplicate - Ignored by system" })
  ).not.toBeInTheDocument()
})
