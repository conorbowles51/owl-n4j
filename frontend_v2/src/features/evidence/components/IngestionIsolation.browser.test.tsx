import "@/styles/globals.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import type { EvidenceJob } from "@/types/evidence.types"
import { JobsPanel } from "./JobsPanel"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-job-progress", () => ({ useJobProgress: vi.fn() }))
vi.mock("../hooks/use-guarded-process", () => ({
  useGuardedProcess: () => ({ start: vi.fn() }),
}))
vi.mock("./ProcessHoldDialog", () => ({ ProcessHoldDialog: () => null }))

it("keeps AI visible through a second reading, failure, resume, completion and reopening", async () => {
  await page.viewport(1280, 900)
  const base = {
    case_id: "synthetic-case",
    batch_id: "ai-batch",
    progress: 0.35,
    error_message: null,
    entity_count: 0,
    relationship_count: 0,
    file_size: 1000,
    mime_type: "application/pdf",
    sha256: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    resumable: true,
  }
  let jobs: EvidenceJob[] = [
    {
      ...base,
      id: "ai-job",
      job_type: "ingestion",
      file_name: "Synthetic chat.pdf",
      status: "extracting_entities",
    },
  ]
  const controls: string[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method === "POST" && url.includes("/resume?")) {
      controls.push(url)
      jobs = jobs.map((job) =>
        job.id === "pdf-job"
          ? { ...job, status: "pending", error_message: null }
          : job
      )
      return { state: "queued", affected_jobs: 1 }
    }
    if (url.startsWith("/api/evidence/engine/jobs?"))
      return jobs.map((job) => ({ ...job }))
    if (url.startsWith("/api/background-tasks?")) return { tasks: [] }
    return []
  })
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const mount = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <div className="mx-auto h-[820px] w-[560px] py-5">
          <JobsPanel caseId="synthetic-case" />
        </div>
      </QueryClientProvider>
    )
  const refresh = () =>
    queryClient.invalidateQueries({
      queryKey: ["evidence-jobs", "synthetic-case"],
    })
  const ai = () =>
    within(
      screen.getByRole("group", { name: "Processing: Synthetic chat.pdf" })
    )
  const pdf = () =>
    within(
      screen.getByRole("group", {
        name: "Financial statement reading: Synthetic statement.pdf",
      })
    )
  try {
    const first = mount()
    await screen.findByText("AI ingestion")
    jobs.push({
      ...base,
      id: "pdf-job",
      batch_id: "pdf-batch",
      job_type: "pdf_review",
      file_name: "Synthetic statement.pdf",
      status: "extracting_text",
      progress: 0.1,
    })
    await refresh()
    await screen.findByText("2 running · 0 queued")
    expect(ai().getByText("Extracting Entities")).toBeTruthy()
    expect(pdf().getByText("Financial statement reading")).toBeTruthy()

    jobs = jobs.map((job) =>
      job.id === "pdf-job"
        ? { ...job, status: "failed", error_message: "Synthetic OCR timeout" }
        : job
    )
    await refresh()
    await waitFor(() => expect(pdf().getByText("Failed")).toBeTruthy())
    expect(ai().getByText("35%")).toBeTruthy()
    expect(screen.getByText("1 running · 0 queued")).toBeTruthy()
    fireEvent.click(pdf().getByRole("button", { name: "Resume batch" }))
    await waitFor(() =>
      expect(controls).toEqual([
        "/api/evidence/engine/jobs/pdf-job/resume?case_id=synthetic-case",
      ])
    )
    await waitFor(() => expect(pdf().getByText("Pending")).toBeTruthy())
    expect(screen.getByText("1 running · 1 queued")).toBeVisible()
    expect(ai().getByText("Extracting Entities")).toBeTruthy()

    jobs = jobs.map((job) =>
      job.id === "pdf-job"
        ? { ...job, status: "completed", progress: 1 }
        : { ...job, progress: 0.48 }
    )
    await refresh()
    await waitFor(() =>
      expect(pdf().getByText("Ready for review")).toBeTruthy()
    )
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

it("pauses a phone report, returns to its saved state and resumes while AI ingestion continues", async () => {
  await page.viewport(1280, 900)
  const base = {
    case_id: "synthetic-case",
    batch_id: null,
    error_message: null,
    sha256: null,
    progress: 0.4,
    entity_count: 0,
    relationship_count: 0,
    file_size: 1000,
    mime_type: "application/xml",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    resumable: true,
  }
  let phone: EvidenceJob = {
    ...base,
    id: "phone-job",
    job_type: "cellebrite_ingestion",
    file_name: "Synthetic phone",
    status: "writing_graph",
  }
  const ai: EvidenceJob = {
    ...base,
    id: "ai-job",
    job_type: "ingestion",
    file_name: "Synthetic document.pdf",
    status: "extracting_entities",
  }
  const calls: string[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.startsWith("/api/evidence/engine/jobs?"))
      return [structuredClone(phone), ai]
    if (url.startsWith("/api/background-tasks?")) return { tasks: [] }
    if (options?.method === "POST" && url.includes("/phone-job/")) {
      calls.push(url)
      if (url.includes("/pause?")) {
        phone.pause_requested = true
        return { state: "pausing", affected_jobs: 1 }
      }
      phone = {
        ...phone,
        paused: false,
        pause_requested: false,
        status: "pending",
      }
      return { state: "queued", affected_jobs: 1 }
    }
    return []
  })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const mount = () =>
    render(
      <QueryClientProvider client={client}>
        <div className="mx-auto h-[820px] max-w-xl p-4">
          <JobsPanel caseId="synthetic-case" />
        </div>
      </QueryClientProvider>
    )
  const refresh = () =>
    client.invalidateQueries({ queryKey: ["evidence-jobs", "synthetic-case"] })
  const card = () =>
    within(screen.getByRole("group", { name: "Processing: Synthetic phone" }))
  try {
    mount()
    await screen.findByText("Cellebrite: Synthetic phone")
    fireEvent.click(card().getByRole("button", { name: "Pause" }))
    await waitFor(() =>
      expect(card().getByRole("button", { name: "Pausing…" })).toBeDisabled()
    )
    expect(screen.getByText("Extracting Entities")).toBeVisible()
    phone = { ...phone, paused: true, status: "pending" }
    await refresh()
    await waitFor(() => expect(card().getByText("Paused")).toBeVisible())
    cleanup()
    client.clear()
    mount()
    await screen.findByRole("button", { name: "Resume" })
    expect(screen.getByText("1 running · 0 queued")).toBeVisible()
    await page.screenshot({ path: "/tmp/loupe-phone-pause-resume.png" })
    fireEvent.click(card().getByRole("button", { name: "Resume" }))
    await waitFor(() => expect(card().getByText("Pending")).toBeVisible())
    expect(calls).toEqual([
      "/api/evidence/engine/jobs/phone-job/pause?case_id=synthetic-case",
      "/api/evidence/engine/jobs/phone-job/resume?case_id=synthetic-case",
    ])
    expect(screen.getByText("Extracting Entities")).toBeVisible()
    phone = { ...phone, status: "completed", progress: 1, entity_count: 40 }
    await refresh()
    await waitFor(() => expect(card().getByText("Completed")).toBeVisible())
    expect(screen.getByText("1 running · 0 queued")).toBeVisible()
  } finally {
    cleanup()
    client.clear()
  }
})
