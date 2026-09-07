import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { CandidateFinalizationPanel } from "./CandidateFinalizationPanel"
afterEach(() => vi.restoreAllMocks())
const ready = {
  case_id: "case-a",
  evidence_file_id: "file-a",
  applied: false,
  revision: "a".repeat(64),
  resolved_count: 2,
  rejected_count: 1,
  proof_class: "p3",
  included_in_default_totals: false,
  file_bytes_verified: true,
  source_sha256: "b".repeat(64),
  byte_count: 123,
  limitation: "Selected rows",
}
const receipt = {
  case_id: "case-a",
  evidence_file_id: "file-a",
  applied: true,
  created: true,
  finalization_id: "seal",
  finalization_revision: ready.revision,
  source_document_id: "doc",
  run_id: "run",
  transaction_count: 2,
  transactions: [1, 2].map((i) => ({
    candidate_id: `c${i}`,
    transaction_id: `t${i}`,
    ref_id: `TX-${i}`,
    superseded_by_id: null,
  })),
  proof_class_at_finalization: "p3",
  included_in_default_totals: false,
  limitation: "Selected rows",
}
const response = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  })
function mount() {
  const client = new QueryClient()
  const rendered = render(
    <QueryClientProvider client={client}>
      <CandidateFinalizationPanel caseId="case-a" fileId="file-a" />
    </QueryClientProvider>
  )
  return { client, ...rendered }
}
async function preview() {
  fireEvent.click(screen.getByRole("button", { name: "Preview finalization" }))
  await screen.findByText(/2 resolved rows will become/)
}
function confirm() {
  fireEvent.click(
    screen.getByRole("checkbox", { name: /These are documentary/ })
  )
  fireEvent.click(screen.getByRole("checkbox", { name: /I accept incomplete/ }))
  fireEvent.change(screen.getByLabelText("Reason for finalization"), {
    target: { value: "Reviewed selected financial rows" },
  })
}
it("requires preview, explicit confirmations and reason before writing", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(response(ready))
    .mockResolvedValue(response(receipt))
  const { client } = mount(),
    invalidate = vi.spyOn(client, "invalidateQueries")
  expect(fetch).not.toHaveBeenCalled()
  await preview()
  expect(
    screen.getByRole("button", { name: "Finalize selected rows" })
  ).toBeDisabled()
  confirm()
  fireEvent.click(
    screen.getByRole("button", { name: "Finalize selected rows" })
  )
  expect(await screen.findByText(/Finalized 2 transactions/)).toBeVisible()
  expect(JSON.parse(fetch.mock.calls[1][1]!.body as string)).toEqual({
    expected_revision: ready.revision,
    documentary_financial_rows: true,
    accept_incomplete_coverage: true,
    reason: "Reviewed selected financial rows",
  })
  expect(invalidate).toHaveBeenCalledWith({
    queryKey: ["financial-ledger", "case-a"],
  })
  expect(
    screen.getByRole("button", { name: "View source: TX-1" })
  ).toBeVisible()
})
it("does not allow double submission while the write is unresolved", async () => {
  let finish!: (value: Response) => void
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(response(ready))
    .mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve
        })
    )
  mount()
  await preview()
  confirm()
  const button = screen.getByRole("button", { name: "Finalize selected rows" })
  fireEvent.click(button)
  fireEvent.click(button)
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
  finish(response(receipt))
  await screen.findByText(/Finalized 2 transactions/)
})
it("requires reload after uncertain failure and resets acceptance", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(response(ready))
    .mockResolvedValueOnce(response({ detail: "Source changed" }, 409))
    .mockResolvedValue(response(ready))
  mount()
  await preview()
  confirm()
  fireEvent.click(
    screen.getByRole("button", { name: "Finalize selected rows" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Reload the preview"
  )
  expect(
    screen.getByRole("button", { name: "Finalize selected rows" })
  ).toBeDisabled()
  fireEvent.click(
    screen.getByRole("button", { name: "Reload finalization preview" })
  )
  await screen.findByText(/2 resolved rows will become/)
  expect(
    screen.getByRole("checkbox", { name: /These are documentary/ })
  ).not.toBeChecked()
  expect(screen.getByLabelText("Reason for finalization")).toHaveValue("")
})
it("refuses a preview belonging to another file", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    response({ ...ready, evidence_file_id: "file-b" })
  )
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Preview finalization" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("different PDF")
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument()
})
it("refuses a receipt for a different preview and invalidates the original case", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(response(ready))
    .mockResolvedValue(
      response({ ...receipt, finalization_revision: "d".repeat(64) })
    )
  const { client } = mount(),
    invalidate = vi.spyOn(client, "invalidateQueries")
  await preview()
  confirm()
  fireEvent.click(
    screen.getByRole("button", { name: "Finalize selected rows" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "does not match this preview"
  )
  expect(screen.queryByText(/Finalized 2 transactions/)).not.toBeInTheDocument()
  expect(invalidate).toHaveBeenCalledWith({
    queryKey: ["financial-candidates", "case-a"],
  })
})
it("shows a stored receipt after reload without offering another write", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(response({ ...receipt, created: false }))
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Preview finalization" }))
  expect(await screen.findByText(/Finalized 2 transactions/)).toBeVisible()
  expect(
    screen.queryByRole("button", { name: "Finalize selected rows" })
  ).not.toBeInTheDocument()
  expect(fetch).toHaveBeenCalledTimes(1)
})
it("invalidates the original case even if the panel closes during a write", async () => {
  let finish!: (value: Response) => void
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(response(ready))
    .mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve
        })
    )
  const { client, unmount } = mount(),
    invalidate = vi.spyOn(client, "invalidateQueries")
  await preview()
  confirm()
  fireEvent.click(
    screen.getByRole("button", { name: "Finalize selected rows" })
  )
  await waitFor(() => expect(finish).toBeDefined())
  unmount()
  finish(response(receipt))
  await waitFor(() =>
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ["financial-ledger", "case-a"],
    })
  )
})
