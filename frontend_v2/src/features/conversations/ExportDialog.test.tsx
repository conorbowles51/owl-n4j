import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

/** 03 section 12.2 and 07 J-14 with the server stubbed. Synthetic data only. */
const api = vi.hoisted(() => ({ describeExport: vi.fn(), createExport: vi.fn(), getExport: vi.fn(), downloadExport: vi.fn() }))
vi.mock("@/features/phones/api", async (orig) => ({ ...(await orig<object>()), ...api }))

import { ExportDialog } from "./ExportDialog"

const facts = { total: 2188, messages: 2140, calls: 48, other: 0, unconfirmed: 412, phones: 3, collapsed_copies: 0, zone: "Eastern Time", left_out: "Saved passwords and card numbers left out.", limits: [] }
const state = (over: object) => ({ export_id: "x1", format: "pdf", source: "stream", state: "queued", progress: 0, counts: {}, file: null, error: null, created_at: null, finished_at: null, ...over })

function show() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <ExportDialog caseId="case-1" filter={{ case_id: "case-1" }} words="between A and B" open onOpenChange={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("Export for counsel", () => {
  it("states the scope and the reading state before drawing, then draws and offers the file", async () => {
    api.describeExport.mockResolvedValue(facts)
    api.createExport.mockResolvedValue({ export_id: "x1" })
    api.getExport.mockResolvedValueOnce(state({ state: "rendering", progress: 0.4 })).mockResolvedValue(state({ state: "done", progress: 1, counts: { total: 2188, missing_characters: 2 }, file: { filename: "between A and B.pdf", size: 10, sha256: "ab12" } }))
    show()
    expect(await screen.findByText("All 2,140 messages and 48 calls, between A and B, on 3 phones, times in Eastern Time. Saved passwords and card numbers left out.")).toBeInTheDocument()
    expect(screen.getByText(/^412 of these 2,188 rows rely on readings not yet confirmed by a person\./)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Review them first." })).toHaveAttribute("href", "/cases/case-1/phone-review")
    fireEvent.click(screen.getByRole("button", { name: "Export PDF" }))
    await waitFor(() => expect(api.createExport).toHaveBeenCalledWith("case-1", { case_id: "case-1" }, { title: "between A and B", words: "between A and B" }, "pdf"))
    expect(await screen.findByText(/^The PDF is ready: 2,188 rows, 2 characters printed as \[U\+\.\.\.\]/, undefined, { timeout: 5000 })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Save the PDF" }))
    await waitFor(() => expect(api.downloadExport).toHaveBeenCalledWith("case-1", "x1", "between A and B.pdf"))
  })

  it("a failed drawing keeps the choices and offers Try again with the reference", async () => {
    api.describeExport.mockResolvedValue(facts)
    api.createExport.mockResolvedValue({ export_id: "x2" })
    api.getExport.mockReset().mockResolvedValue(state({ export_id: "x2", state: "failed", error: "The export could not be drawn. Your choices are kept; try again. Reference: ab12cd34." }))
    show()
    await screen.findByText(/^All 2,140 messages/)
    fireEvent.click(screen.getByRole("button", { name: "Export PDF" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Reference: ab12cd34.")
    expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled()
  })

  it("makes one RSMF file for a review platform and says how many attachments are listed without their file", async () => {
    api.describeExport.mockResolvedValue(facts)
    api.createExport.mockReset().mockResolvedValue({ export_id: "x3" })
    api.getExport.mockReset().mockResolvedValue(state({ export_id: "x3", format: "rsmf", state: "done", progress: 1,
      counts: { total: 2188, rsmf: { events: 2188, attachments_not_included: 3 } }, file: { filename: "between A and B.rsmf", size: 10, sha256: "cd34" } }))
    show()
    await screen.findByText(/^All 2,140 messages/)
    fireEvent.click(screen.getByLabelText("RSMF for a review platform"))
    expect(screen.getByText(/the whole period in one conversation file/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Export RSMF" }))
    await waitFor(() => expect(api.createExport).toHaveBeenCalledWith("case-1", { case_id: "case-1" }, { title: "between A and B", words: "between A and B" }, "rsmf"))
    expect(await screen.findByText(/^The RSMF file is ready: 2,188 rows, 3 attachments listed without the file; each says why\./)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Save the RSMF file" }))
    await waitFor(() => expect(api.downloadExport).toHaveBeenCalledWith("case-1", "x3", "between A and B.rsmf"))
    expect(document.body.textContent).not.toMatch(/—/)
  })
})
