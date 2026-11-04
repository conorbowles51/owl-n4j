import { afterEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { CaseworkReportCard } from "./CaseworkReportCard"
import { moveSection } from "../casework-report"

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

afterEach(() => vi.restoreAllMocks())

describe("casework report (FEAT-003 findings first with linked evidence; FEAT-009 section order)", () => {
  it("moves sections and keeps the order in bounds", () => {
    expect(moveSection(["findings", "theories", "notes"], 2, -1)).toEqual(["findings", "notes", "theories"])
    expect(moveSection(["findings", "theories", "notes"], 0, -1)).toEqual(["findings", "theories", "notes"])
  })

  it("sends the chosen sections in the chosen order with the marking", async () => {
    URL.createObjectURL = vi.fn(() => "blob:x")
    URL.revokeObjectURL = vi.fn()
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(new Blob(["%PDF"]), { status: 200, headers: { "Content-Disposition": 'attachment; filename="casework-report.pdf"' } }),
    )
    render(<CaseworkReportCard caseId="case-1" />)
    fireEvent.click(screen.getByLabelText(/\. Notes$/)) // include notes (off by default)
    fireEvent.click(screen.getByRole("button", { name: "Move notes up" }))
    fireEvent.change(screen.getByLabelText("Casework report privilege marking"), { target: { value: "privileged_confidential" } })
    fireEvent.click(screen.getByRole("button", { name: /Export casework report/ }))
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled())
    const [url, init] = fetchSpy.mock.calls[0]
    expect(url).toBe("/api/workspace/case-1/report")
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({
      sections: ["findings", "notes", "theories"],
      privilege_marking: "privileged_confidential",
    })
  })
})
