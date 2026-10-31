import { describe, expect, it } from "vitest"
import type { EvidenceJob } from "@/types/evidence.types"
import { hasUnfinishedJobs, jobsPollInterval } from "./use-jobs"

const job = (status: string, paused = false) => ({ id: status, status, paused }) as unknown as EvidenceJob

describe("jobsPollInterval", () => {
  it("does not poll a watched list whose jobs have all completed or failed", () => {
    expect(jobsPollInterval(true, [job("completed"), job("failed")])).toBe(false)
    expect(jobsPollInterval(true, [])).toBe(false)
    expect(jobsPollInterval(true, undefined)).toBe(false)
  })

  it("polls every 5 s while any job is unfinished, paused jobs included", () => {
    expect(jobsPollInterval(true, [job("completed"), job("extracting_text")])).toBe(5000)
    expect(jobsPollInterval(true, [job("pending", true)])).toBe(5000)
  })

  it("never polls an unwatched list", () => {
    expect(jobsPollInterval(false, [job("pending")])).toBe(false)
  })

  it("marks unfinished jobs for the Processing tab dot", () => {
    expect(hasUnfinishedJobs([job("completed")])).toBe(false)
    expect(hasUnfinishedJobs([job("writing_graph")])).toBe(true)
  })
})
