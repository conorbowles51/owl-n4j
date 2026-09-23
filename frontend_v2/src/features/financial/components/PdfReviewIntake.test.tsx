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
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { expect, it, vi, afterEach } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { PdfReviewIntake } from "./PdfReviewIntake"
import { uploadOrdinaryFiles } from "@/features/evidence/resumable-upload"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("@/features/evidence/resumable-upload", () => ({
  uploadOrdinaryFiles: vi.fn(),
}))
vi.mock("@/features/evidence/components/ResumableUploadsPanel", () => ({
  ResumableUploadsPanel: () => null,
}))
afterEach(() => vi.resetAllMocks())
function mount() {
  const onReady = vi.fn()
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <PdfReviewIntake caseId="case" onReady={onReady} />
    </QueryClientProvider>
  )
  return onReady
}
const uploaded = {
  id: "file",
  case_id: "case",
  original_filename: "bank.pdf",
  status: "unprocessed",
  stored_path: "synthetic/bank.pdf",
  size: 3,
  sha256: "synthetic",
  created_at: "2026-09-23T00:00:00Z",
}
it("uploads then explicitly requests local preparation and opens prepared rows", async () => {
  vi.mocked(uploadOrdinaryFiles).mockResolvedValue({ files: [uploaded] })
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    String(url).includes("/process/background")
      ? { job_ids: ["job"] }
      : {
          id: "job",
          case_id: "case",
          job_type: "pdf_review",
          status: "completed",
          quality_report: { preparation_mode: "pdf_review" },
        }
  )
  const ready = mount()
  fireEvent.change(screen.getByLabelText("PDF document"), {
    target: {
      files: [new File(["pdf"], "bank.pdf", { type: "application/pdf" })],
    },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare PDF for review" })
  )
  fireEvent.click(
    await screen.findByRole("button", { name: "Open PDF review" })
  )
  expect(ready).toHaveBeenCalledOnce()
  expect(
    vi
      .mocked(fetchAPI)
      .mock.calls.find(([url]) =>
        String(url).includes("/process/background")
      )?.[1]?.body
  ).toEqual({
    case_id: "case",
    file_ids: ["file"],
    preparation_mode: "pdf_review",
  })
})
it("uses an existing uploaded PDF without uploading again", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    String(url).includes("/process/background")
      ? { job_ids: ["job"] }
      : String(url).includes("/engine/jobs/")
        ? {
            id: "job",
            case_id: "case",
            job_type: "pdf_review",
            status: "failed",
          }
        : { files: [uploaded] }
  )
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Find uploaded PDFs" }))
  fireEvent.click(
    await screen.findByRole("button", { name: /Use uploaded PDF/ })
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare PDF for review" })
  )
  await screen.findByText(/The PDF could not be read/)
  expect(
    vi
      .mocked(fetchAPI)
      .mock.calls.some(([url]) => String(url).endsWith("/upload"))
  ).toBe(false)
})
it("does not show another case's preparation as ready", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    String(url).includes("/process/background")
      ? { job_ids: ["job"] }
      : String(url).includes("/engine/jobs/")
        ? {
            id: "job",
            case_id: "other",
            job_type: "pdf_review",
            status: "completed",
          }
        : { files: [uploaded] }
  )
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Find uploaded PDFs" }))
  fireEvent.click(
    await screen.findByRole("button", { name: /Use uploaded PDF/ })
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare PDF for review" })
  )
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("does not match")
  )
  expect(
    screen.queryByRole("button", { name: "Open PDF review" })
  ).not.toBeInTheDocument()
})
