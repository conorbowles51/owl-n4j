import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { CandidateDocumentProgress } from "./CandidateDocumentProgress"
afterEach(() => vi.restoreAllMocks())
const zero = { pending: 0, resolved: 0, rejected: 0 }
const answer = {
  case_id: "case", evidence_file_id: "file", filename: "statement.pdf", counts: { ...zero, pending: 1 }, unlocated_readings: 0,
  applied: false, limitation: "Selected rows do not prove completeness.", pages: [
    { page_number: 1, prepared: true, counts: zero, batches: [] },
    { page_number: 2, prepared: true, counts: { ...zero, pending: 1 }, batches: [{ ...zero, pending: 1, mapping_id: "batch", next_pending_candidate_id: "row" }] },
  ],
}
function mount(data: unknown = answer) {
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(data)))
  const open = vi.fn()
  render(<QueryClientProvider client={new QueryClient()}><CandidateDocumentProgress caseId="case" fileId="file" onOpenReading={open} /></QueryClientProvider>)
  return { fetch, open }
}
it("loads on request, distinguishes unselected pages and resumes the pending reading", async () => {
  const { fetch, open } = mount()
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Show document progress" }))
  expect(await screen.findByText("No saved rows selected. Check this page for transactions, fees and interest.")).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Continue page 2, batch 1" }))
  expect(open).toHaveBeenCalledWith("batch", "row")
})
it.each([
  { evidence_file_id: "other" },
  { counts: zero },
  { pages: [{ ...answer.pages[0], page_number: 2 }] },
])("refuses wrong document or inconsistent counts %j", async change => {
  mount({ ...answer, ...change })
  fireEvent.click(screen.getByRole("button", { name: "Show document progress" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("Document progress unavailable")
})
