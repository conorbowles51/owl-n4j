import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import { PhoneReportsPanel } from "./PhoneReportsPanel"
import { consequenceText, phoneReportsAPI, replaceTargets, retireCandidates, type PhoneReport } from "../phone-reports"

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const report = (over: Partial<PhoneReport>): PhoneReport => ({
  id: "x", case_id: "c", label: "Report", standing: "active", capture_state: "captured", record_count: 10,
  file_count: 2, created_at: "2026-10-30T10:00:00Z", captured_at: "2026-10-30T11:00:00Z",
  extracted_from: null, extracted_to: null, supersedes_id: null, superseded_at: null, superseded_reason: null,
  superseded_by: null, replaced_by_id: null, possible_same_device: [], ...over,
})

const older = report({ id: "old", label: "First copy", extracted_from: "2026-03-02T09:00:00+00:00" })
const newer = report({ id: "new", label: "Second copy", possible_same_device: [{ extraction_id: "old", name: "First copy" }] })

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <PhoneReportsPanel caseId="c" />
    </QueryClientProvider>
  )
}

afterEach(() => vi.restoreAllMocks())

describe("phone reports: Replace and Retire (01 section 10.7)", () => {
  it("states the consequence with the report's own extraction date", () => {
    expect(consequenceText(older)).toBe(
      "First copy (extracted Mar 2, 2026) will be retired. Its records stay readable and marked as from a replaced report."
    )
    expect(consequenceText(report({ label: "No date" }))).toContain("No date (read into the case Oct 30, 2026)")
  })

  it("offers Replace only on the newer report naming the older one still in use", () => {
    expect(replaceTargets(newer, [older, newer]).map((r) => r.id)).toEqual(["old"])
    expect(replaceTargets(older, [older, newer])).toEqual([])
    expect(replaceTargets(newer, [{ ...older, standing: "superseded" }, newer])).toEqual([])
    expect(replaceTargets({ ...newer, capture_state: "capturing" }, [older, newer])).toEqual([])
    expect(retireCandidates(older, [older, newer, report({ id: "p", standing: "pending", capture_state: "capturing" })]).map((r) => r.id)).toEqual(["new"])
  })

  it("I-2: Replace needs a typed reason, retires the older report, and the count changes once", async () => {
    const after = [
      { ...older, standing: "superseded" as const, superseded_at: "2026-11-01T12:00:00Z", superseded_reason: "Full copy", superseded_by: "Investigator", replaced_by_id: "new" },
      { ...newer, supersedes_id: "old" },
    ]
    let state = [older, newer]
    vi.spyOn(phoneReportsAPI, "list").mockImplementation(async () => state)
    const supersede = vi.spyOn(phoneReportsAPI, "supersede").mockImplementation(async () => {
      state = after
      return after
    })
    renderPanel()
    expect(await screen.findByText("Phone reports: 2 in use")).toBeTruthy()
    expect(screen.getByText(/appears to be from the same phone as First copy/)).toBeTruthy()
    fireEvent.click(screen.getByText("Replace First copy"))
    expect(screen.getByText(/First copy \(extracted Mar 2, 2026\) will be retired/)).toBeTruthy()
    const confirm = screen.getByText("Retire First copy").closest("button") as HTMLButtonElement
    expect(confirm.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "   " } })
    expect(confirm.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: " Full copy " } })
    fireEvent.click(confirm)
    await waitFor(() => expect(supersede).toHaveBeenCalledWith("new", "old", "Full copy"))
    expect(await screen.findByText("Phone reports: 1 in use, 1 not in use")).toBeTruthy()
    expect(screen.getAllByText(/Phone reports:/)).toHaveLength(1)
    expect(screen.getByText(/From a replaced report: replaced by Second copy, retired on Nov 1, 2026 by Investigator\. Reason: Full copy/)).toBeTruthy()
    expect(screen.queryByText(/Replace First copy/)).toBeNull()
    expect(screen.queryByText(/appears to be from the same phone/)).toBeNull()
  })

  it("shows nothing when the case has no phone reports", async () => {
    const list = vi.spyOn(phoneReportsAPI, "list").mockResolvedValue([])
    const { container } = renderPanel()
    await waitFor(() => expect(list).toHaveBeenCalled())
    expect(container.textContent).toBe("")
  })
})
