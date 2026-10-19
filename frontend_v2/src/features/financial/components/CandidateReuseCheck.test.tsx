import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { CandidateReuseCheck } from "./CandidateReuseCheck"
afterEach(() => vi.restoreAllMocks())
const baseline = {
  case_id: "case-a",
  evidence_file_id: "file-a",
  counts: { pending: 2, resolved: 1, rejected: 1 },
  active_readings: 3,
  pairs_examined: 3,
  total_pairs: 3,
  comparison_complete: true,
  source_reuse_pairs: 1,
  unavailable_pairs: 0,
  findings: [
    {
      kind: "same_stored_row",
      left: {
        candidate_id: "c1",
        mapping_id: "m1",
        row_index: 0,
        status: "pending",
      },
      right: {
        candidate_id: "c2",
        mapping_id: "m2",
        row_index: 0,
        status: "resolved",
      },
    },
  ],
  findings_truncated: false,
  revision: "a".repeat(64),
  applied: false,
  scope: "Saved readings",
  limitation: "Snapshot only",
}
function server(value: unknown = baseline, status = 200) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(
      new Response(JSON.stringify(value), {
        status,
        headers: { "Content-Type": "application/json" },
      })
    )
}
function mount() {
  const onOpenReading = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <CandidateReuseCheck
        caseId="case-a"
        fileId="file-a"
        onOpenReading={onOpenReading}
      />
    </QueryClientProvider>
  )
  return onOpenReading
}
it("only checks on request and can open the exact competing reading", async () => {
  const fetch = server(),
    open = mount()
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Check source reuse" }))
  expect(
    await screen.findByText("The same stored row was selected more than once.")
  ).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Open second reading: source row 1 (resolved)",
    })
  )
  expect(open).toHaveBeenCalledWith("m2", "c2")
  expect(screen.getByText(/Snapshot only/)).toBeVisible()
})
it("makes incomplete comparison coverage explicit", async () => {
  server({
    ...baseline,
    pairs_examined: 1,
    comparison_complete: false,
    findings_truncated: true,
  })
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Check source reuse" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("incomplete check")
  expect(screen.getByText(/Showing the first 1 findings/)).toBeVisible()
})
it("refuses a result for another source file", async () => {
  server({ ...baseline, evidence_file_id: "file-b" })
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Check source reuse" }))
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "does not match this PDF"
  )
  expect(
    screen.queryByText("The same stored row was selected more than once.")
  ).not.toBeInTheDocument()
})
it("refuses contradictory complete-coverage claims", async () => {
  server({ ...baseline, pairs_examined: 1 })
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Check source reuse" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("stated coverage")
})
it("does not retain a clean-looking old result when a rerun fails", async () => {
  const fetch = server()
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Check source reuse" }))
  await screen.findByText("The same stored row was selected more than once.")
  fetch.mockResolvedValue(
    new Response(JSON.stringify({ detail: "Source changed" }), {
      status: 409,
      headers: { "Content-Type": "application/json" },
    })
  )
  fireEvent.click(screen.getByRole("button", { name: "Check source reuse" }))
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Source changed")
  )
  expect(
    screen.queryByText("The same stored row was selected more than once.")
  ).not.toBeInTheDocument()
})
