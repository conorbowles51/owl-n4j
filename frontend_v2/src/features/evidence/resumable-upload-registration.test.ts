import { describe, expect, it, vi } from "vitest"

/** Registration is a job the page follows (lx-uploadfollow C): the server answers ``complete`` before a large
 * selection is registered, and the page asks how far it has come; no request timeout bounds a selection's size. */
const api = vi.hoisted(() => ({ fetchAPI: vi.fn() }))
vi.mock("@/lib/api-client", async (orig) => ({ ...(await orig<object>()), ...api }))

import { ApiError } from "@/lib/api-client"
import { REGISTRATION_RESTARTS, REGISTRATION_STOPPED, registerGroup, type Registration } from "./resumable-upload-groups"
import { describeUploadProgress, type UploadProgress } from "./upload-progress"

const group = (status: string, registration?: Registration) => ({
  id: "g-1", case_id: "case-1", folder_id: null, name: "Phone", kind: "folder", status, replace_existing: false,
  file_count: 5000, staged_count: 5000, size: 1, received_bytes: 1,
  receipt: status === "completed" ? { file_ids: ["f"], job_ids: [], message: "Uploaded 5,000 files." } : null,
  ...(registration ? { registration } : {}),
})
const running = (done: number, phase: Registration["phase"] = "checking") =>
  group("uploading", { state: "running", phase, done, total: 5000 })
const noWait = () => Promise.resolve()

describe("registering a selection", () => {
  it("follows a registration the server is still doing until the receipt, reporting n of N", async () => {
    api.fetchAPI.mockReset()
    const polls = [running(2400), running(5000, "saving"), group("completed")]
    api.fetchAPI.mockImplementation(async (url: string, init?: { method?: string; timeout?: number }) => {
      if (url.endsWith("/complete")) {
        expect(init?.method).toBe("POST")
        expect(init?.timeout).toBeLessThanOrEqual(2 * 60 * 1000)
        return running(100)
      }
      if (url.endsWith("/registration")) return polls.shift()
      throw new Error(`unexpected ${url}`)
    })
    const steps: Registration[] = []
    const receipt = await registerGroup("g-1", (step) => steps.push(step), noWait)
    expect(receipt.status).toBe("completed")
    expect(steps.map((s) => [s.done, s.phase])).toEqual([[100, "checking"], [2400, "checking"], [5000, "saving"]])
    expect(api.fetchAPI.mock.calls.filter(([url]) => url.endsWith("/complete"))).toHaveLength(1)
  })

  it("returns at once when the server registered it within its answer", async () => {
    api.fetchAPI.mockReset()
    api.fetchAPI.mockResolvedValueOnce(group("completed"))
    expect((await registerGroup("g-1", undefined, noWait)).receipt?.message).toBe("Uploaded 5,000 files.")
    expect(api.fetchAPI).toHaveBeenCalledTimes(1)
  })

  it("starts a registration again when it stopped on the server (a restart), and gives up after a few", async () => {
    api.fetchAPI.mockReset()
    let starts = 0
    api.fetchAPI.mockImplementation(async (url: string) => {
      if (url.endsWith("/complete")) return ++starts === 2 ? group("completed") : running(10)
      return group("uploading", { state: "stopped", phase: "checking", done: 10, total: 5000 })
    })
    expect((await registerGroup("g-1", undefined, noWait)).status).toBe("completed")
    expect(starts).toBe(2)

    api.fetchAPI.mockReset()
    starts = 0
    api.fetchAPI.mockImplementation(async (url: string) => {
      if (url.endsWith("/complete")) { starts++; return group("uploading", { state: "idle" }) }
      throw new Error(`unexpected ${url}`)
    })
    await expect(registerGroup("g-1", undefined, noWait)).rejects.toThrow(REGISTRATION_STOPPED)
    expect(starts).toBe(REGISTRATION_RESTARTS + 1)
  })

  it("says why when registration failed, and keeps asking through a restart's failed requests", async () => {
    api.fetchAPI.mockReset()
    const answers: unknown[] = [
      new ApiError("Bad gateway", 502),
      new TypeError("Failed to fetch"),
      group("uploading", { state: "failed", error: { status_code: 409, detail: "A saved upload failed verification. No evidence was registered." } }),
    ]
    api.fetchAPI.mockImplementation(async (url: string) => {
      if (url.endsWith("/complete")) return running(1)
      const next = answers.shift()
      if (next instanceof Error) throw next
      return next
    })
    await expect(registerGroup("g-1", undefined, noWait)).rejects.toThrow(
      "A saved upload failed verification. No evidence was registered.",
    )
  })

  it("passes a refusal of complete straight to the page", async () => {
    api.fetchAPI.mockReset()
    api.fetchAPI.mockRejectedValueOnce(new ApiError("Resume this selection before completing it", 409))
    await expect(registerGroup("g-1", undefined, noWait)).rejects.toThrow("Resume this selection before completing it")
    expect(api.fetchAPI).toHaveBeenCalledTimes(1)
  })
})

describe("registration in words", () => {
  const base: UploadProgress = {
    phase: "registering", filesDone: 0, filesTotal: 5000, bytesDone: 1, bytesTotal: 1, startedAt: 0, bytesAtStart: 0,
    kind: "folder",
  }
  it("says how many of the files are registered and what the server is doing", () => {
    expect(describeUploadProgress(base, 0)).toBe(
      "All 5,000 files arrived. Saving them to the case and checking for phone reports.",
    )
    expect(describeUploadProgress({ ...base, filesDone: 1234, registrationPhase: "checking" }, 0)).toBe(
      "Registering 1,234 of 5,000 files: checking each against its fingerprint.",
    )
    expect(describeUploadProgress({ ...base, filesDone: 5000, registrationPhase: "phones" }, 0)).toBe(
      "Registering 5,000 of 5,000 files: checking for phone reports.",
    )
    expect(describeUploadProgress({ ...base, filesDone: 5000, registrationPhase: "saving" }, 0)).toBe(
      "Registering 5,000 of 5,000 files: saving them to the case.",
    )
  })
})
