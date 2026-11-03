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
