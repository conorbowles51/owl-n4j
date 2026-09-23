import "@/styles/globals.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import type { EvidenceJob } from "@/types/evidence.types"
import { JobsPanel } from "./JobsPanel"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()), fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-job-progress", () => ({ useJobProgress: vi.fn() }))
vi.mock("../hooks/use-guarded-process", () => ({ useGuardedProcess: () => ({ start: vi.fn() }) }))
vi.mock("./ProcessHoldDialog", () => ({ ProcessHoldDialog: () => null }))

it("keeps AI visible through a second reading, failure, resume, completion and reopening", async () => {
  await page.viewport(1280, 900)
  const base = {
    case_id: "synthetic-case", batch_id: "ai-batch", progress: .35,
    error_message: null, entity_count: 0, relationship_count: 0,
    file_size: 1000, mime_type: "application/pdf", sha256: null,
    created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    resumable: true,
  }
  let jobs: EvidenceJob[] = [{ ...base, id: "ai-job", job_type: "ingestion",
    file_name: "Synthetic chat.pdf", status: "extracting_entities" }]
  const controls: string[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method === "POST" && url.includes("/resume?")) {
      controls.push(url)
      jobs = jobs.map((job) => job.id === "pdf-job" ? { ...job, status: "pending", error_message: null } : job)
      return { state: "queued", affected_jobs: 1 }
    }
    if (url.startsWith("/api/evidence/engine/jobs?")) return jobs.map((job) => ({ ...job }))
    if (url.startsWith("/api/background-tasks?")) return { tasks: [] }
    return []
  })
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const mount = () => render(<QueryClientProvider client={queryClient}>
    <div className="mx-auto h-[820px] w-[560px] py-5"><JobsPanel caseId="synthetic-case" /></div>
  </QueryClientProvider>)
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["evidence-jobs", "synthetic-case"] })
  const ai = () => within(screen.getByRole("group", { name: "Processing: Synthetic chat.pdf" }))
  const pdf = () => within(screen.getByRole("group", { name: "Financial statement reading: Synthetic statement.pdf" }))
  try {
    const first = mount()
    await screen.findByText("AI ingestion")
    jobs.push({ ...base, id: "pdf-job", batch_id: "pdf-batch", job_type: "pdf_review",
      file_name: "Synthetic statement.pdf", status: "extracting_text", progress: .1 })
    await refresh()
    await screen.findByText("2 active")
    expect(ai().getByText("Extracting Entities")).toBeTruthy()
    expect(pdf().getByText("Financial statement reading")).toBeTruthy()

    jobs = jobs.map((job) => job.id === "pdf-job" ? { ...job, status: "failed", error_message: "Synthetic OCR timeout" } : job)
    await refresh()
    await waitFor(() => expect(pdf().getByText("Failed")).toBeTruthy())
    expect(ai().getByText("35%")).toBeTruthy()
    expect(screen.getByText("1 active")).toBeTruthy()
    fireEvent.click(pdf().getByRole("button", { name: "Resume batch" }))
    await waitFor(() => expect(controls).toEqual(["/api/evidence/engine/jobs/pdf-job/resume?case_id=synthetic-case"]))
    await waitFor(() => expect(pdf().getByText("Pending")).toBeTruthy())
    expect(ai().getByText("Extracting Entities")).toBeTruthy()

    jobs = jobs.map((job) => job.id === "pdf-job" ? { ...job, status: "completed", progress: 1 } : { ...job, progress: .48 })
    await refresh()
    await waitFor(() => expect(pdf().getByText("Ready for review")).toBeTruthy())
    expect(pdf().getByText(/Reading the PDF does not import them/)).toBeTruthy()
    expect(pdf().queryByText("0 entities")).toBeNull()
    expect(ai().getByText("48%")).toBeTruthy()

    first.unmount()
    queryClient.clear()
    mount()
    await screen.findByText("Ready for review")
    expect(ai().getByText("48%")).toBeTruthy()
    await page.screenshot({ path: "/tmp/loupe-ingestion-isolation.png" })
  } finally {
    cleanup()
    queryClient.clear()
  }
})
