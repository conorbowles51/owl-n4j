import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { ReprocessStatement } from "./ReprocessStatement"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("@/features/auth/hooks/use-auth", () => ({
  useAuthStore: (select: (state: unknown) => unknown) =>
    select({ user: { id: "owner" } }),
}))
const key = "loupe-statement-reprocessing:owner:case:file"
const requestId = "957c795a-8e4c-467f-bf18-c198d7c884f7"
const receipt = { case_id: "case", evidence_file_id: "new-file", job_id: "job" }
function mount() {
  const ready = vi.fn()
  const view = render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ReprocessStatement caseId="case" fileId="file" onReady={ready} />
    </QueryClientProvider>
  )
  return { ready, ...view }
}
beforeEach(() => {
  sessionStorage.clear()
  vi.mocked(fetchAPI).mockReset()
})
it("resumes a saved job without starting another version and lets the user open its result", async () => {
  sessionStorage.setItem(key, JSON.stringify({ requestId, receipt }))
  vi.mocked(fetchAPI).mockResolvedValue({
    id: "job",
    case_id: "case",
    job_type: "pdf_review",
    status: "completed",
    quality_report: { preparation_mode: "pdf_review" },
  })
  const { ready } = mount()
  fireEvent.click(
    await screen.findByRole("button", { name: "Open new reading" })
  )
  expect(ready).toHaveBeenCalledWith("new-file")
  expect(fetchAPI).toHaveBeenCalledTimes(1)
  expect(fetchAPI).toHaveBeenCalledWith("/api/evidence/engine/jobs/job")
})
it("reuses the saved request when its response was interrupted", async () => {
  sessionStorage.setItem(key, JSON.stringify({ requestId, receipt: null }))
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    String(url).includes("/reprocess?")
      ? receipt
      : {
          id: "job",
          case_id: "case",
          job_type: "pdf_review",
          status: "processing",
        }
  )
  const view = mount()
  fireEvent.click(screen.getByRole("button", { name: "Reprocess statement" }))
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      expect.stringContaining("/file/reprocess?"),
      { method: "POST", body: { request_id: requestId } }
    )
  )
  await waitFor(() =>
    expect(JSON.parse(sessionStorage.getItem(key)!).receipt).toEqual(receipt)
  )
  view.unmount()
})
it("does not open a completed job returned for another case", async () => {
  sessionStorage.setItem(key, JSON.stringify({ requestId, receipt }))
  vi.mocked(fetchAPI).mockResolvedValue({
    id: "job",
    case_id: "another-case",
    job_type: "pdf_review",
    status: "completed",
    quality_report: { preparation_mode: "pdf_review" },
  })
  const { ready } = mount()
  await screen.findByRole("alert")
  expect(ready).not.toHaveBeenCalled()
  expect(
    screen.queryByRole("button", { name: "Open new reading" })
  ).not.toBeInTheDocument()
})
