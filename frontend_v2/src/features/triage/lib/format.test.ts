import { describe, expect, it } from "vitest"
import { formatBytes, normalizeCategoryRows, stageProgress } from "./format"

describe("triage format helpers", () => {
  it("formats byte counts with stable units", () => {
    expect(formatBytes(0)).toBe("0 B")
    expect(formatBytes(512)).toBe("512 B")
    expect(formatBytes(1536)).toBe("1.5 KB")
    expect(formatBytes(2 * 1024 * 1024)).toBe("2.0 MB")
  })

  it("normalizes profile category maps and row arrays", () => {
    expect(normalizeCategoryRows({ documents: 3 })).toEqual([
      { category: "documents", count: 3, total_size: 0, top_extensions: [] },
    ])
    expect(normalizeCategoryRows([{ label: "images", value: "4", size: 120 }])).toEqual([
      { category: "images", count: 4, total_size: 120, top_extensions: [] },
    ])
  })

  it("computes bounded stage progress", () => {
    expect(stageProgress({ files_total: 10, files_processed: 3 })).toBe(30)
    expect(stageProgress({ files_total: 10, files_processed: 12 })).toBe(100)
    expect(stageProgress({ files_total: 0, files_processed: 5 })).toBe(100)
  })
})
