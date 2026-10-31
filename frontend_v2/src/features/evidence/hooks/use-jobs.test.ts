import { describe, expect, it } from "vitest"
import type { EvidenceJob } from "@/types/evidence.types"
import { IDLE_JOBS_POLL_MS, hasUnfinishedJobs, jobsPollInterval } from "./use-jobs"

const job = (status: string, paused = false) => ({ id: status, status, paused }) as unknown as EvidenceJob

describe("jobsPollInterval", () => {
  it("checks a watched list with nothing running once a minute, so jobs started elsewhere still appear", () => {
    expect(IDLE_JOBS_POLL_MS).toBe(60_000)
    expect(jobsPollInterval(true, [job("completed"), job("failed")])).toBe(IDLE_JOBS_POLL_MS)
    expect(jobsPollInterval(true, [])).toBe(IDLE_JOBS_POLL_MS)
  })

  it("retries a failed fetch every 5 s", () => {
    expect(jobsPollInterval(true, undefined, true)).toBe(5000)
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
