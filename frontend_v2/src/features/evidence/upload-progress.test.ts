import { describe, expect, it } from "vitest"
import {
  addFileCost,
  describeUploadProgress,
  FIRST_RUN_TEXT,
  type FileCostFit,
  percentOf,
  type UploadProgress,
} from "./upload-progress"

/** n finished files of the given size, each taking the given seconds. */
const fitOf = (files: [number, number][], times = 1): FileCostFit | undefined => {
  let fit: FileCostFit | undefined
  for (let i = 0; i < times; i++) for (const [size, seconds] of files) fit = addFileCost(fit, size, seconds)
  return fit
}

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

  it("gives one file's time left from the measured byte rate of this step", () => {
    // 1 GB in 60 s, 5.4 GB to go: about 324 s
    const p = { ...base, filesDone: 0, filesTotal: 1, bytesDone: 1024 ** 3 }
    expect(describeUploadProgress(p, 60_000)).toBe("Checking the file before upload: 1.0 of 6.4 GB, about 5 min left")
  })

  it("does not take a phone folder's time from the bytes of its large files", () => {
    // The live C3 shape: 801 MB in 43,123 files; large files went first, so 300 MB were hashed in 30 s with no file
    // finished. A byte rate promised under a minute for what took 402 s.
    const p: UploadProgress = { ...base, filesDone: 0, filesTotal: 43123, bytesDone: 300e6, bytesTotal: 801e6 }
    expect(describeUploadProgress(p, 30_000)).toBe(`Checking files before upload: 0 of 43,123, ${FIRST_RUN_TEXT}`)
    // then 1,000 small files at 9 ms each, after one 300 MB file in 30 s: per file and per byte both count
    const fit = fitOf([[300e6, 30]].concat(Array(1000).fill([10e3, 0.009])) as [number, number][])
    const later = { ...p, filesDone: 1001, bytesDone: 310e6, fit }
    // 42,122 files at 8 ms plus 491 MB at 0.1 s/MB: 386 s
    expect(describeUploadProgress(later, 45_000)).toBe("Checking files before upload: 1,001 of 43,123, about 6 min left")
  })

  it("waits for enough finished files before giving a many-file time left", () => {
    const p: UploadProgress = { ...base, fit: fitOf([[10e3, 0.01]], 19), filesDone: 19 }
    expect(describeUploadProgress(p, 60_000)).toContain(FIRST_RUN_TEXT)
    expect(describeUploadProgress({ ...p, fit: fitOf([[10e3, 0.01]], 20), filesDone: 20 }, 60_000)).toContain("min left")
  })

  it("names the sending step and how to continue, measuring only files sent in this run", () => {
    // resumed: 12,400 files already there; 100 sent in this run at 50 ms each and 10 KB, 30,644 to go: about 26 min
    const p: UploadProgress = { ...base, phase: "sending", bytesDone: 2.1 * 1024 ** 3, bytesAtStart: 1.1 * 1024 ** 3,
      filesDone: 12500, fit: fitOf([[10e3, 0.05]], 100) }
    expect(describeUploadProgress(p, 100_000)).toBe(
      "Sending 2.1 of 6.4 GB, about 26 min left. If this tab closes, choose the same folder again to continue."
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
