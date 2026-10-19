import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { StatementRowAssignment } from "./StatementRowAssignment"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
beforeEach(() => {
  vi.mocked(fetchAPI).mockReset()
})
const check = (count: number, status: string) => ({
  transaction_count: count,
  checks: [{ kind: "closing_balance", status }],
})
const result = {
  case_id: "case",
  evidence_file_id: "file",
  revision: "preview-version",
  applied: false,
  moved_rows: 1,
  affected_reviews: 2,
  statements: [
    {
      statement_id: "source",
      label: "Source account",
      before: check(3, "matches"),
      after: check(2, "difference"),
    },
    {
      statement_id: "target",
      label: "Destination account",
      before: check(3, "unavailable"),
      after: check(4, "unavailable"),
    },
  ],
}
function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const props = {
    caseId: "case",
    fileId: "file",
    rowIds: ["row"],
    reason: "Checked printed account",
    reviewRevision: "saved-review",
    batchId: "batch",
    request: {
      expected_revision: "reading",
      rows: [{ id: "row", description: "Current correction" }],
    },
    choices: [
      {
        id: "target",
        institution: "Synthetic Bank",
        account_reference: "5678",
        period_start: "2020-06-12",
        period_end: "2020-07-11",
        page_numbers: [2],
      },
    ],
    onApplied: vi.fn().mockResolvedValue(undefined),
    onBusy: vi.fn(),
  }
  const view = render(
    <QueryClientProvider client={client}>
      <StatementRowAssignment {...props} />
    </QueryClientProvider>
  )
  fireEvent.change(screen.getByLabelText("Move to account and period"), {
    target: { value: "target" },
  })
  return {
    props,
    rerender: (request: typeof props.request) =>
      view.rerender(
        <QueryClientProvider client={client}>
          <StatementRowAssignment {...props} request={request} />
        </QueryClientProvider>
      ),
  }
}
it("shows both affected statements before saving exact reviewed values", async () => {
  vi.mocked(fetchAPI)
    .mockResolvedValueOnce(result)
    .mockResolvedValueOnce({ ...result, applied: true })
  const { props } = setup()
  fireEvent.click(screen.getByRole("button", { name: "Preview move" }))
  expect(
    await screen.findByText("3 transactions before; 2 after.")
  ).toBeInTheDocument()
  expect(
    screen.getByText("3 transactions before; 4 after.")
  ).toBeInTheDocument()
  expect(screen.getByText("Difference to check")).toBeInTheDocument()
  expect(props.onApplied).not.toHaveBeenCalled()
  fireEvent.click(
    screen.getByRole("button", { name: "Save move of 1 transaction" })
  )
  await waitFor(() => expect(props.onApplied).toHaveBeenCalledOnce())
  expect(vi.mocked(fetchAPI).mock.calls[1][1]?.body).toMatchObject({
    request: props.request,
    row_ids: ["row"],
    target_statement_id: "target",
    batch_id: "batch",
    expected_review_revision: "saved-review",
    expected_preview: "preview-version",
  })
  expect(props.onBusy.mock.calls.map((call) => call[0])).toEqual([true, false])
})
it("invalidates preview when corrected values change and keeps failed moves editable", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(result)
  const { props, rerender } = setup()
  fireEvent.click(screen.getByRole("button", { name: "Preview move" }))
  await screen.findByRole("button", { name: "Save move of 1 transaction" })
  rerender({
    ...props.request,
    rows: [{ id: "row", description: "A later correction" }],
  })
  expect(
    screen.queryByRole("button", { name: "Save move of 1 transaction" })
  ).not.toBeInTheDocument()
  expect(screen.getByRole("alert")).toHaveTextContent("Preview the move again")
  fireEvent.click(screen.getByRole("button", { name: "Preview move" }))
  await screen.findByRole("button", { name: "Save move of 1 transaction" })
  vi.mocked(fetchAPI).mockRejectedValueOnce(
    new Error("Another reviewer saved the destination. Preview again.")
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Save move of 1 transaction" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent("Another reviewer")
  expect(props.onApplied).not.toHaveBeenCalled()
  expect(screen.getByLabelText("Move to account and period")).toHaveValue(
    "target"
  )
})
