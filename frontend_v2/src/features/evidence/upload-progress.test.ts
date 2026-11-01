import { describe, expect, it } from "vitest"
import { describeUploadProgress, FIRST_RUN_TEXT, percentOf, type UploadProgress } from "./upload-progress"

const base: UploadProgress = {
  phase: "hashing",
  filesDone: 12400,
  filesTotal: 43144,
  bytesDone: 0,
  bytesTotal: 6.4 * 1024 ** 3,
  startedAt: 0,
  bytesAtStart: 0,
  kind: "folder",
}

describe("upload progress words (07 J-1, 4.7)", () => {
  it("says it is working out time left until a rate has been measured", () => {
    expect(describeUploadProgress({ ...base, bytesDone: 100 }, 1000)).toBe(
      `Checking files before upload: 12,400 of 43,144, ${FIRST_RUN_TEXT}`
    )
  })

  it("gives time left from the measured rate of this step", () => {
    // 1 GB in 60 s, 5.4 GB to go: about 324 s
    const p = { ...base, bytesDone: 1024 ** 3 }
    expect(describeUploadProgress(p, 60_000)).toBe("Checking files before upload: 12,400 of 43,144, about 5 min left")
  })

  it("names the sending step and how to continue, measuring only bytes sent in this run", () => {
    const p: UploadProgress = { ...base, phase: "sending", bytesDone: 2.1 * 1024 ** 3, bytesAtStart: 1.1 * 1024 ** 3 }
    expect(describeUploadProgress(p, 100_000)).toBe(
      "Sending 2.1 of 6.4 GB, about 7 min left. If this tab closes, choose the same folder again to continue."
    )
    expect(describeUploadProgress({ ...p, kind: "archive" }, 100_000)).toContain("choose the same file again")
  })

  it("never shows 100% before the files are registered", () => {
    expect(percentOf({ ...base, phase: "sending", bytesDone: base.bytesTotal })).toBe(99)
    expect(percentOf({ ...base, phase: "registering" })).toBe(100)
  })

  it("has no em dashes", () => {
    for (const phase of ["hashing", "sending", "registering"] as const)
      expect(describeUploadProgress({ ...base, phase }, 5000)).not.toContain("—")
  })
})
