import { describe, expect, it, vi } from "vitest"

/** A file over the server's per-file limit is refused before any hashing or request, with the reason in words. */
const api = vi.hoisted(() => ({ fetchAPI: vi.fn() }))
vi.mock("@/lib/api-client", async (orig) => ({ ...(await orig<object>()), ...api }))

import { MAX_FILE_BYTES, uploadFolderOrArchive } from "./resumable-upload-groups"

const fake = (name: string, size: number) => ({ name, size, slice: vi.fn(), webkitRelativePath: "" }) as unknown as File

describe("upload size limit", () => {
  it("refuses a ZIP over the limit before hashing it", async () => {
    const zip = fake("report.zip", Math.round(9.8 * 1024 ** 3))
    await expect(uploadFolderOrArchive("case-1", [zip], { isArchive: true } as never)).rejects.toThrow(
      "This ZIP file is 9.8 GB; one file can be at most 8 GB, so it was not uploaded. Unpack it and upload the report folder instead.",
    )
    expect(zip.slice).not.toHaveBeenCalled()
    expect(api.fetchAPI).not.toHaveBeenCalled()
  })

  it("names the file in a folder that is over the limit", async () => {
    const small = fake("a.db", 10)
    const big = fake("big.bin", MAX_FILE_BYTES + 1)
    await expect(uploadFolderOrArchive("case-1", [small, big], {} as never)).rejects.toThrow(
      "big.bin is 8.0 GB; one file can be at most 8 GB, so nothing was uploaded.",
    )
    expect(small.slice).not.toHaveBeenCalled()
  })
})

describe("resuming a saved upload", () => {
  const state = {
    id: "g-1", case_id: "case-1", folder_id: null, name: "r", kind: "folder", status: "paused", replace_existing: false,
    file_count: 1, staged_count: 0, size: 10, received_bytes: 0, receipt: null,
    members: [{ id: "m-1", path: "r/a.db", size: 10, sha256: "a".repeat(64), status: "uploading", received: [] }],
  }
  const file = () => ({ name: "a.db", size: 10, webkitRelativePath: "r/a.db", slice: vi.fn(() => new Blob(["0123456789"])) }) as unknown as File
  const stopAfterResume = () => {
    api.fetchAPI.mockReset()
    api.fetchAPI.mockImplementation(async (url: string, init?: { method?: string }) => {
      if (url === "/api/evidence-upload-groups/g-1" && !init) return state
      if (init?.method === "POST" && url.endsWith("/resume")) return {}
      throw new Error("stop here")
    })
  }

  it("does not read again a file the same selection already fingerprinted and matched", async () => {
    stopAfterResume()
    const { resumeUploadGroup } = await import("./resumable-upload-groups")
    const f = file()
    await resumeUploadGroup("g-1", [f], undefined, new Map([["r/a.db", "a".repeat(64)]])).catch(() => null)
    expect(f.slice).not.toHaveBeenCalled()
    expect(api.fetchAPI).toHaveBeenCalledWith("/api/evidence-upload-groups/g-1/resume", { method: "POST" })
  })

  it("still checks a file it has not fingerprinted, and refuses a changed one", async () => {
    stopAfterResume()
    const { resumeUploadGroup } = await import("./resumable-upload-groups")
    const f = file()
    await expect(resumeUploadGroup("g-1", [f])).rejects.toThrow("The original file r/a.db is missing or has changed.")
    expect(f.slice).toHaveBeenCalled()
  })
})

describe("small files in batches", () => {
  const member = (i: number, size: number) =>
    ({ id: `m-${i}`, path: `r/${i}`, size, chunk_size: 4 * 1024 * 1024, status: "uploading" }) as never
  it("packs at most 500 files and 4 MiB a batch, in order, and always at least one file", async () => {
    const { takeBatch, isBatchable, BATCH_FILE_BYTES } = await import("./resumable-upload-groups")
    const small = Array.from({ length: 1200 }, (_, i) => member(i, 100))
    const sizes = [takeBatch(small), takeBatch(small), takeBatch(small)].map((b) => b.length)
    expect(sizes).toEqual([500, 500, 200])
    expect(small).toEqual([])
    const big = [member(0, 3 * 1024 * 1024), member(1, 2 * 1024 * 1024)]
    expect(takeBatch(big).map((m: { id: string }) => m.id)).toEqual(["m-0"])
    expect(isBatchable(member(0, BATCH_FILE_BYTES))).toBe(true)
    expect(isBatchable(member(0, BATCH_FILE_BYTES + 1))).toBe(false)
  })
})
