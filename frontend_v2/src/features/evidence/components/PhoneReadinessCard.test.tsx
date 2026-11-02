import { render, screen, fireEvent } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import type { EvidenceJob } from "@/types/evidence.types"
import { PhoneReadinessCard } from "./PhoneReadinessCard"
import { CANCEL_KEEPS, measureOf, outcomeLines, PHONE_STALL_SECONDS, stepIndex, stepText } from "../phone-readiness"

const job = (over: Partial<EvidenceJob> = {}): EvidenceJob => ({
  id: "j1", case_id: "c", batch_id: null, job_type: "phone_capture", file_name: "Handset", status: "capturing",
  progress: 40, error_message: null, entity_count: 0, relationship_count: 0, file_size: 0, mime_type: null,
  sha256: null, created_at: "2026-11-01T12:00:00Z", updated_at: "2026-11-01T12:00:00Z", resumable: true,
  ...over,
})

describe("phone readiness card (07 J-1a)", () => {
  it("lists every stage in words with true counts", () => {
    render(<PhoneReadinessCard job={job({ pipeline_state: { phone: { stage: "capturing", counts: { records: 12400, files: 300, bytes_read: 10, bytes_total: 100 } } } })} />)
    expect(screen.getByText("Getting Handset ready")).toBeTruthy()
    expect(screen.getByText("Checking the report")).toBeTruthy()
    expect(screen.getByText("Reading records")).toBeTruthy()
    expect(screen.getByText("Checking nothing is missing")).toBeTruthy()
    expect(screen.getByText(/12,400 records and 300 files read/)).toBeTruthy()
    expect(screen.getByText(/, working out time left \(first run of this step\)/)).toBeTruthy()
  })

  it("maps engine stages to the three steps", () => {
    expect([stepIndex("counting"), stepIndex("capturing"), stepIndex("indexing_files"), stepIndex("finishing")]).toEqual([0, 1, 2, 3])
    expect(stepText("indexing_files", { files_checked: 1200, files_total: 21000 })).toBe("Checking the files: 1,200 of 21,000")
  })

  it("counts the entries compared inside a document, so a long check shows progress", () => {
    expect(stepText("reconciling", { documents_done: 0, documents_total: 1, entries_checked: 12000, entries_total: 71045 }))
      .toBe("Comparing every element with the report: 12,000 of 71,045 entries")
    expect(stepText("reconciling", { documents_done: 1, documents_total: 3, entries_checked: 500, entries_total: 9000 }))
      .toBe("Comparing every element with the report: document 2 of 3, 500 of 9,000 entries")
    expect(stepText("reconciling", { documents_done: 0, documents_total: 1 })).toBe("Comparing every element with the report: document 1 of 1")
    expect(measureOf("reconciling", { documents_done: 0, documents_total: 1, entries_checked: 5, entries_total: 10 })).toEqual([5, 10, "entries"])
    expect(measureOf("reconciling", { documents_done: 1, documents_total: 3, entries_checked: 5, entries_total: 10 })).toEqual([1, 3, "documents"])
  })

  it("says what Cancel keeps before cancelling", () => {
    const onCancel = vi.fn()
    render(<PhoneReadinessCard job={job()} onCancel={onCancel} />)
    fireEvent.click(screen.getByText("Cancel"))
    expect(screen.getByText(CANCEL_KEEPS)).toBeTruthy()
    expect(onCancel).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText("Cancel the reading"))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it("a report that finished while a release flagged it paused offers no Resume", () => {
    const onResume = vi.fn()
    render(<PhoneReadinessCard job={job({ status: "completed", paused: true, pipeline_state: { phone: { stage: "finishing" } } })} onResume={onResume} onClear={vi.fn()} />)
    expect(screen.queryByText("Resume")).toBeNull()
    expect(screen.getByText("Clear")).toBeTruthy()
  })

  it("applies the stall rule after 30 s without change", () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-11-01T12:01:00Z"))
    render(<PhoneReadinessCard job={job({ id: "j-stall", pipeline_state: { phone: { stage: "capturing", changed_at: "2026-11-01T12:00:20Z" } } })} />)
    expect(PHONE_STALL_SECONDS).toBe(30)
    expect(screen.getByText(/No change on reading records for 40 s\. The server is still on this step\./)).toBeTruthy()
    vi.useRealTimers()
  })

  it("reports file outcomes with counts and a failure with its reference", () => {
    expect(outcomeLines({ match: 21153, missing: 247, empty_placeholder: 21643 })).toEqual([
      "21,153 files match the report's fingerprint",
      "247 files are listed in the report but not in the production",
      "21,643 files are empty placeholders for files the production did not include",
    ])
    render(<PhoneReadinessCard job={job({ status: "failed", error_message: "Reading stopped at the step shown.", pipeline_state: { phone: { stage: "capturing", failure_stage: "capturing", reference: "ref-1" } } })} onResume={() => {}} />)
    expect(screen.getByText(/Reference ref-1/)).toBeTruthy()
    expect(screen.getByText("Try again")).toBeTruthy()
  })
})
