import { describe, expect, it, vi } from "vitest"

/** A file over the server's per-file limit is refused before any hashing or request, with the reason in words. */
const api = vi.hoisted(() => ({ fetchAPI: vi.fn() }))
vi.mock("@/lib/api-client", async (orig) => ({ ...(await orig<object>()), ...api }))

import { uploadFingerprint } from "./resumable-upload"
import { MAX_FILE_BYTES, resumeUploadGroup, uploadFolderOrArchive } from "./resumable-upload-groups"
import { describeUploadProgress, type UploadProgress } from "./upload-progress"

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

describe("picking a folder again", () => {
  const SAVED = 5000
  const LEFT = 30
  const sha = (seed: number) => seed.toString(16).padStart(64, "0")
  type Picked = File & { slice: ReturnType<typeof vi.fn> }
  const picked = (i: number, lastModified = 1000): Picked => {
    const bytes = `file ${i}`
    return {
      name: `${i}.bin`,
      size: bytes.length,
      lastModified,
      webkitRelativePath: `r/${i}.bin`,
      slice: vi.fn(() => new Blob([bytes])),
    } as unknown as Picked
  }
  const hashOf = async (file: File) => (await uploadFingerprint(file)).sha256
  const selection = async (
    files: Picked[],
    { saved, modified = 1000 }: { saved: number; modified?: number | null },
  ) => {
    const members = await Promise.all(
      files.map(async (file, i) => ({
        id: `m-${i}`, path: file.webkitRelativePath, size: file.size, sha256: await hashOf(file),
        chunk_size: 4 * 1024 * 1024, received: [], status: i < saved ? "staged" : "uploading", modified,
      })),
    )
    for (const file of files) file.slice.mockClear()
    return {
      id: "g-1", case_id: "case-1", folder_id: null, name: "r", kind: "folder", status: "uploading",
      replace_existing: false, file_count: files.length, staged_count: saved, size: 1, received_bytes: 0, receipt: null,
      members,
    }
  }
  /** Answers as the server does and stops at the first send: what was read before it is what is measured. */
  const server = (group: Awaited<ReturnType<typeof selection>>) => {
    api.fetchAPI.mockReset()
    api.fetchAPI.mockImplementation(async (url: string, init?: { method?: string; body?: BodyInit }) => {
      if (url.startsWith("/api/evidence-upload-groups?")) return [group]
      if (url === "/api/evidence-upload-groups/g-1" && !init) return group
      if (url === "/api/evidence-upload-groups" && init?.method === "POST") throw new Error("started a new selection")
      if (init?.method === "PUT") throw new Error("first send")
      throw new Error(`unexpected ${url}`)
    })
  }
  const reads = (files: Picked[]) => files.filter((file) => file.slice.mock.calls.length).length
  const firstSend = (files: Picked[], seen: UploadProgress[] = []) =>
    uploadFolderOrArchive("case-1", files, { isFolder: true, onProgress: (p) => seen.push(p) })

  it("reads only the files still to send and says what it matched and on what", async () => {
    const files = Array.from({ length: SAVED + LEFT }, (_, i) => picked(i))
    server(await selection(files, { saved: SAVED }))
    const seen: UploadProgress[] = []
    await expect(firstSend(files, seen)).rejects.toThrow()
    expect(reads(files)).toBe(LEFT)
    expect(reads(files.slice(0, SAVED))).toBe(0)
    const checking = seen.find((p) => p.phase === "hashing")!
    expect(checking.filesTotal).toBe(LEFT)
    expect(describeUploadProgress(checking, 0)).toContain(
      "5,000 saved files matched by name, size and modified time. Checking files before upload: 0 of 30",
    )
    const sending = seen.find((p) => p.phase === "sending")!
    expect(sending.filesDone).toBe(SAVED)
    expect(describeUploadProgress(sending, 0)).toContain(
      "5,000 saved files matched by name, size and modified time, not read again.",
    )
  })

  it("matches a selection begun before modified times were kept on name and size, and says only that", async () => {
    const files = Array.from({ length: 12 }, (_, i) => picked(i, 5000 + i))
    server(await selection(files, { saved: 10, modified: null }))
    const seen: UploadProgress[] = []
    await expect(firstSend(files, seen)).rejects.toThrow()
    expect(reads(files)).toBe(2)
    expect(describeUploadProgress(seen.find((p) => p.phase === "sending")!, 0)).toContain(
      "10 saved files matched by name and size, not read again.",
    )
  })

  it("reads a saved file whose modified time moved, and carries on when its bytes are the same", async () => {
    const files = Array.from({ length: 4 }, (_, i) => picked(i))
    const group = await selection(files, { saved: 3 })
    group.members[1].modified = 999
    server(group)
    await expect(firstSend(files)).rejects.toThrow("first send")
    expect(files.map((file) => file.slice.mock.calls.length > 0)).toEqual([false, true, false, true])
  })

  it("starts a new selection when a saved file with a moved time holds other bytes, reading each file once", async () => {
    const files = Array.from({ length: 4 }, (_, i) => picked(i))
    const group = await selection(files, { saved: 3 })
    group.members[1].modified = 999
    group.members[1].sha256 = sha(1)
    server(group)
    await expect(firstSend(files)).rejects.toThrow("started a new selection")
    for (const file of files) expect(file.slice).toHaveBeenCalledTimes(1)
  })

  it("reads nothing against a selection the folder cannot be: a file of another size", async () => {
    const files = Array.from({ length: 4 }, (_, i) => picked(i))
    const group = await selection(files, { saved: 3 })
    group.members[2].size += 1
    server(group)
    await expect(firstSend(files)).rejects.toThrow("started a new selection")
    const body = api.fetchAPI.mock.calls.find(([url, init]) => url === "/api/evidence-upload-groups" && init?.method)
    expect(body?.[1].body.members.map((m: { modified: number }) => m.modified)).toEqual([1000, 1000, 1000, 1000])
  })

  it("the Reselect path reads a chosen saved file that no longer matches and refuses it when its bytes differ", async () => {
    const files = Array.from({ length: 3 }, (_, i) => picked(i))
    const group = await selection(files, { saved: 2 })
    group.members[0].modified = 999
    group.members[0].sha256 = sha(1)
    server(group)
    await expect(resumeUploadGroup("g-1", files)).rejects.toThrow("The original file r/0.bin is missing or has changed.")
    expect(files.map((file) => file.slice.mock.calls.length > 0)).toEqual([true, false, true])
  })

  it("the Reselect path needs no saved file in the selection and reads only the files still to send", async () => {
    const files = Array.from({ length: 3 }, (_, i) => picked(i))
    server(await selection(files, { saved: 2 }))
    await expect(resumeUploadGroup("g-1", files.slice(2))).rejects.toThrow("first send")
    expect(reads(files)).toBe(1)
  })
})

describe("whole-selection caps, before hashing (01 D41)", () => {
  it("refuses a selection of more files than an upload takes, in words, reading nothing", async () => {
    const { selectionRefusal, MAX_SELECTION_FILES } = await import("./resumable-upload-groups")
    api.fetchAPI.mockReset()
    const small = fake("a.db", 10)
    const over = Array.from({ length: MAX_SELECTION_FILES + 1 }, () => small)
    await expect(uploadFolderOrArchive("case-1", over, {} as never)).rejects.toThrow(
      "This selection holds 1,000,001 files and an upload takes up to 1,000,000. Nothing was read or sent. " +
        "Upload it in parts, for example one folder at a time."
    )
    expect(small.slice).not.toHaveBeenCalled()
    expect(api.fetchAPI).not.toHaveBeenCalled()
    expect(selectionRefusal([{ size: 10 }])).toBeNull()
  })

  it("refuses a selection over 64 GB before hashing, naming its size", async () => {
    api.fetchAPI.mockReset()
    const eightGB = 8 * 1024 ** 3
    const files = Array.from({ length: 9 }, (_, i) => fake(`${i}.bin`, eightGB))
    await expect(uploadFolderOrArchive("case-1", files, {} as never)).rejects.toThrow(
      "This selection is 72.0 GB and an upload can hold up to 64 GB. Nothing was read or sent. " +
        "Split it into smaller selections."
    )
    expect(files[0].slice).not.toHaveBeenCalled()
    expect(api.fetchAPI).not.toHaveBeenCalled()
  })
})

describe("a file list larger than one page (01 D41)", () => {
  const item = (i: number) => ({ path: `P/${i}`, size: 1, sha256: "a".repeat(64), chunks: ["a".repeat(64)] })
  const meta = { id: "g-9", case_id: "case-1", folder_id: null, name: "P", kind: "folder" as const, replace_existing: false }

  it("declares the whole size, sends the rest in pages, and resolves with the full list", async () => {
    const { registerByPages } = await import("./resumable-upload-groups")
    const manifest = Array.from({ length: 5 }, (_, i) => item(i))
    api.fetchAPI.mockReset()
    api.fetchAPI.mockImplementation(async (url: string, init?: { method?: string; body?: unknown }) => {
      if (init?.method === "POST" && url === "/api/evidence-upload-groups") return { id: "g-9" }
      if (init?.method === "POST" && url === "/api/evidence-upload-groups/g-9/members") return { id: "g-9" }
      if (url === "/api/evidence-upload-groups/g-9") return { id: "g-9", members: manifest }
      throw new Error(`unexpected ${url}`)
    })
    await expect(registerByPages(meta, manifest, 2)).resolves.toMatchObject({ id: "g-9" })
    const posts = api.fetchAPI.mock.calls.filter(([, init]) => (init as { method?: string })?.method === "POST")
    expect(posts[0][1].body).toMatchObject({ members_total: 5, members: manifest.slice(0, 2) })
    expect(posts.map(([url]) => url)).toEqual([
      "/api/evidence-upload-groups",
      "/api/evidence-upload-groups/g-9/members",
      "/api/evidence-upload-groups/g-9/members",
    ])
    expect(posts[1][1].body).toMatchObject({ members: manifest.slice(2, 4) })
    expect(posts[2][1].body).toMatchObject({ members: manifest.slice(4) })
  })

  it("says so when the list did not finish arriving", async () => {
    const { registerByPages } = await import("./resumable-upload-groups")
    const manifest = Array.from({ length: 3 }, (_, i) => item(i))
    api.fetchAPI.mockReset()
    api.fetchAPI.mockImplementation(async (url: string) =>
      url === "/api/evidence-upload-groups/g-9" ? { id: "g-9", members: manifest.slice(0, 2) } : { id: "g-9" }
    )
    await expect(registerByPages(meta, manifest, 2)).rejects.toThrow(
      "The selection's file list did not finish arriving. Try the upload again; the files already listed are kept."
    )
  })
})
