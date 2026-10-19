import "@/styles/globals.css"
import { page, userEvent } from "vitest/browser"
import { render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { FilePreviewPanel } from "./FilePreviewPanel"
import type { EvidenceFile } from "@/types/evidence.types"

vi.mock("./previews/PdfPreview", () => ({ PdfPreview: ({ evidenceId }: { evidenceId: string }) =>
  <div className="border bg-white text-black p-8 min-h-[440px]" data-testid="pdf">
    <h2 className="text-xl font-semibold">Original bank statement</h2><p>Source citation: {evidenceId}</p>
  </div> }))

it("explains one PDF and opens each retained reading without changing the original", async () => {
  await page.viewport(1180, 820)
  const file = { id: "original", original_filename: "Example statement.pdf", reading_versions: [
    { id: "reading-1", status: "processed", created_at: "2026-09-21T10:00:00Z" },
    { id: "reading-2", status: "processed", created_at: "2026-09-22T10:00:00Z" },
  ] } as EvidenceFile
  render(<main className="p-5 bg-background text-foreground"><h1 className="text-xl mb-4">Example statement.pdf</h1>
    <FilePreviewPanel file={file} caseId="case" /></main>)
  await userEvent.click(screen.getByText("Reading history · one original PDF"))
  expect(screen.getByText(/not additional uploads/)).toBeVisible()
  await userEvent.selectOptions(screen.getByLabelText("PDF reading version"), "reading-1")
  expect(screen.getByText("Source citation: reading-1")).toBeVisible()
  await userEvent.selectOptions(screen.getByLabelText("PDF reading version"), "reading-2")
  expect(screen.getByText("Source citation: reading-2")).toBeVisible()
  await userEvent.selectOptions(screen.getByLabelText("PDF reading version"), "original")
  expect(screen.getByText("Source citation: original")).toBeVisible()
  await page.screenshot({ path: "/tmp/evidence-reading-history.png" })
})
