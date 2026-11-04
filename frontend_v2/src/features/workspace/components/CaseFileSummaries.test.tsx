import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import type { EvidenceFile } from "@/types/evidence.types"
import { CaseFileSummaries } from "./CaseFileSummaries"
import { filesWithSummaries } from "../lib/file-summaries"

const file = (id: string, summary: string | null, processed_at: string) =>
  ({ id, original_filename: `${id}.pdf`, summary, processed_at, created_at: processed_at }) as unknown as EvidenceFile

const files = [
  file("old", "## Overview\\nOlder document.", "2026-05-01"),
  file("none", null, "2026-06-01"),
  file("new", "## Overview\\nNewest document about the wire.", "2026-10-01"),
  file("blank", "  ", "2026-10-02"),
]
let current: EvidenceFile[] = files
vi.mock("@/features/evidence/hooks/use-evidence", () => ({
  useEvidence: () => ({ data: current, isLoading: false, isError: false }),
}))

describe("file summaries in the Workspace (FEAT-001)", () => {
  it("lists only files with a summary, newest first, and counts against all files", () => {
    const out = filesWithSummaries(files)
    expect(out.summarised.map((f) => f.id)).toEqual(["new", "old"])
    expect(out.total).toBe(4)
  })

  it("shows each summary inline, labelled as AI-made, and opens the file", () => {
    current = files
    const onOpen = vi.fn()
    render(<CaseFileSummaries caseId="c" onOpen={onOpen} />)
    expect(screen.getByText("2 of 4 files have an AI summary.", { exact: false })).toBeInTheDocument()
    expect(screen.getAllByText("AI summary")).toHaveLength(2)
    expect(screen.getByText(/Newest document about the wire/)).toBeInTheDocument()
    fireEvent.click(screen.getByText("new.pdf"))
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: "new" }))
  })

  it("says plainly when no file has a summary", () => {
    current = [file("none", null, "2026-06-01")]
    render(<CaseFileSummaries caseId="c" onOpen={() => {}} />)
    expect(screen.getByText("No file summaries yet")).toBeInTheDocument()
    expect(screen.getByText(/1 file in this case; none has an AI summary/)).toBeInTheDocument()
  })
})
