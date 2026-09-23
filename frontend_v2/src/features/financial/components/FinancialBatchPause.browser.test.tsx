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
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { FinancialBatchPanel } from "./FinancialBatchPanel"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))

it("retains a paused import across navigation and separately pauses a PDF reading without affecting AI", async () => {
  await page.viewport(1080, 850)
  let state = "preparing"
  let pdfPaused = false
  const controls: string[] = []
  const batch = {
    id: "batch",
    case_id: "case",
    files: [
      {
        source_id: "file",
        file_id: "file",
        filename: "Synthetic.pdf",
        status: "processing",
      },
    ],
    reading_job_ids: ["pdf"],
    counts: { pending_import: 1 },
    available_statements: 1,
    available_transactions: 12,
    ready_transactions: 12,
    ready_revision: "a".repeat(64),
    total: 0,
    items: [],
    operations: [],
  }
  const base = {
    case_id: "case",
    batch_id: "reading",
    status: "extracting_text",
    progress: 0.4,
    resumable: true,
    file_size: 100,
    mime_type: "application/pdf",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/control/") && options?.method === "POST") {
      controls.push(url)
      state = url.includes("/pause?") ? "paused" : "preparing"
      return { status: state }
    }
    if (url.includes("/engine/jobs/pdf/") && options?.method === "POST") {
      controls.push(url)
      pdfPaused = url.includes("/pause?")
      return {}
    }
    if (url.startsWith("/api/evidence/engine/jobs?"))
      return [
        {
          ...base,
          id: "pdf",
          file_name: "Synthetic.pdf",
          job_type: "pdf_review",
          paused: pdfPaused,
        },
        {
          ...base,
          id: "ai",
          file_name: "Synthetic chat.pdf",
          job_type: "ingestion",
          status: "extracting_entities",
        },
      ]
    if (url.startsWith("/api/financial/statement-import/batches/batch?"))
      return { ...batch, status: state }
    if (url.includes("/confirm")) throw Error("A paused import must not submit")
    return []
  })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const mount = () =>
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter
          initialEntries={["/cases/case/financial?view=statements&batch=batch"]}
        >
          <main className="mx-auto max-w-5xl p-5">
            <FinancialBatchPanel caseId="case" />
          </main>
        </MemoryRouter>
      </QueryClientProvider>
    )
  try {
    const first = mount()
    fireEvent.click(
      await screen.findByRole("button", { name: "Pause batch preparation" })
    )
    await screen.findByRole("button", { name: "Resume batch preparation" })
    expect(screen.getByRole("button", { name: /Import 12/ })).toBeDisabled()
    fireEvent.click(
      screen.getByText("PDF reading jobs · pause or resume a reading")
    )
    const pdf = within(
      await screen.findByRole("group", {
        name: "Financial statement reading: Synthetic.pdf",
      })
    )
    fireEvent.click(pdf.getByRole("button", { name: /Pause/ }))
    await waitFor(() => expect(pdfPaused).toBe(true))
    first.unmount()
    client.clear()
    mount()
    await screen.findByRole("button", { name: "Resume batch preparation" })
    fireEvent.click(
      screen.getByText("PDF reading jobs · pause or resume a reading")
    )
    fireEvent.click(
      within(
        await screen.findByRole("group", {
          name: "Financial statement reading: Synthetic.pdf",
        })
      ).getByRole("button", { name: /Resume/ })
    )
    await waitFor(() => expect(pdfPaused).toBe(false))
    fireEvent.click(
      screen.getByRole("button", { name: "Resume batch preparation" })
    )
    await screen.findByRole("button", { name: "Pause batch preparation" })
    expect(controls).toHaveLength(4)
    expect(controls.every((url) => !url.includes("/ai/"))).toBe(true)
    await page.viewport(390, 844)
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(392)
    await page.screenshot({ path: "/tmp/loupe-batch-resume-mobile.png" })
  } finally {
    cleanup()
    client.clear()
  }
})
