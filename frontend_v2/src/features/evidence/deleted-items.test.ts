import { describe, expect, it } from "vitest"
import { purgeSummary, size } from "./deleted-items"

describe("purgeSummary", () => {
  it("says what a removal for good took, including files kept because another item uses them", () => {
    expect(
      purgeSummary("uploadfollow-2000", {
        rows_removed: 3,
        folders_removed: 2,
        files_removed: 2,
        files_kept_shared: 1,
        bytes_on_disk_freed: 2 * 1024 * 1024,
      })
    ).toBe(
      "Removed uploadfollow-2000 for good: 3 records, 2 folders, 2 files removed from disk, " +
        "1 files kept because another item still uses them, 2.0 MB freed"
    )
  })

  it("says so when nothing else was left", () => {
    expect(purgeSummary(null, {})).toBe("Removed the item for good: nothing else was left")
  })

  it("sizes in GB", () => {
    expect(size(3 * 1024 * 1024 * 1024)).toBe("3.0 GB")
  })
})
