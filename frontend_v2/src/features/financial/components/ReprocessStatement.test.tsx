// This existing workflow fixture has case editing and upload access.
vi.mock("../hooks/use-financial-access", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../hooks/use-financial-access")>()),
  useFinancialAccess: () => ({
    canEdit: true,
    canUpload: true,
    ready: true,
    error: false,
  }),
}))
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
      {
        method: "POST",
        body: { request_id: requestId, reading_mode: "automatic" },
      }
    )
  )
  await waitFor(() =>
    expect(JSON.parse(sessionStorage.getItem(key)!).receipt).toEqual(receipt)
  )
  view.unmount()
})
it("keeps the selected image reading method through an interrupted request and refresh", async () => {
  vi.mocked(fetchAPI).mockRejectedValue(new Error("Connection interrupted"))
  const first = mount()
  fireEvent.click(screen.getByText("Read the statement again", { exact: true }))
  fireEvent.change(screen.getByLabelText("Reading method"), {
    target: { value: "page_images" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Reprocess statement" }))
  await screen.findByRole("alert")
  const stored = JSON.parse(sessionStorage.getItem(key)!)
  expect(stored.readingMode).toBe("page_images")
  expect(screen.getByLabelText("Reading method")).toBeDisabled()
  first.unmount()
  vi.mocked(fetchAPI).mockResolvedValue(receipt)
  const next = mount()
  expect(screen.getByLabelText("Reading method")).toHaveValue("page_images")
  expect(screen.getByLabelText("Reading method")).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Reprocess statement" }))
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      expect.stringContaining("/file/reprocess?"),
      {
        method: "POST",
        body: { request_id: stored.requestId, reading_mode: "page_images" },
      }
    )
  )
  next.unmount()
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

it("does not open an automatic reading as the requested image reading", async () => {
  sessionStorage.setItem(
    key,
    JSON.stringify({ requestId, receipt, readingMode: "page_images" })
  )
  vi.mocked(fetchAPI).mockResolvedValue({
    id: "job",
    case_id: "case",
    job_type: "pdf_review",
    status: "completed",
    quality_report: {
      preparation_mode: "pdf_review",
      pdf_reading_mode: "automatic",
    },
  })
  const { ready } = mount()
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "did not confirm that it read from page images"
  )
  expect(ready).not.toHaveBeenCalled()
  expect(
    screen.queryByRole("button", { name: "Open new reading" })
  ).not.toBeInTheDocument()
})
