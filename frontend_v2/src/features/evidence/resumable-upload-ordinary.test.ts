import { beforeEach, describe, expect, it, vi } from "vitest"

/** An ordinary file selection: a file over the limit is named before any hashing, and one refused or failed file
 * never stops the others (12 Nov: a 1.3 GB video refused after minutes of hashing, and nothing of the selection
 * was delivered). */
const api = vi.hoisted(() => ({ fetchAPI: vi.fn() }))
vi.mock("@/lib/api-client", async (orig) => ({ ...(await orig<object>()), ...api }))

import { MAX_ORDINARY_FILE_BYTES, uploadOrdinaryFiles } from "./resumable-upload"

const big = (name: string, size: number) => ({ name, size, slice: vi.fn() }) as unknown as File
const small = (name: string, text: string) => {
  const blob = new Blob([text])
  return { name, size: blob.size, slice: vi.fn((a?: number, b?: number) => blob.slice(a, b)) } as unknown as File
}

const sessions = new Map<string, { filename: string; size: number }>()
let failName = ""
const calls: string[] = []

beforeEach(() => {
  sessions.clear()
  calls.length = 0
  failName = ""
  api.fetchAPI.mockReset()
  api.fetchAPI.mockImplementation(async (url: string, init?: { method?: string; body?: unknown; timeout?: number }) => {
    calls.push(`${init?.method || "GET"} ${url}`)
    const snap = (id: string, status = "uploading", received: number[] = []) => ({
      id, case_id: "case-1", folder_id: null, filename: sessions.get(id)!.filename, size: sessions.get(id)!.size,
      sha256: "a".repeat(64), chunk_size: 4 * 1024 * 1024, received, status,
      evidence_id: status === "completed" ? `ev-${id}` : null,
    })
    if (url.startsWith("/api/evidence-upload-sessions?")) return []
    if (url === "/api/evidence-upload-sessions" && init?.method === "POST") {
      const body = init.body as { id: string; filename: string; size: number }
      if (body.filename === failName) throw new Error("Storage is full")
      sessions.set(body.id, body)
      return snap(body.id)
    }
    const m = url.match(/^\/api\/evidence-upload-sessions\/([^/]+)(?:\/(.*))?$/)
    if (m && !m[2]) return snap(m[1])
    if (m && m[2].startsWith("chunks/")) return snap(m[1], "uploading", [0])
    if (m && m[2] === "complete") {
      expect(init?.timeout).toBe(3_600_000)
      return snap(m[1], "completed", [0])
    }
    if (url.startsWith("/api/evidence/ev-")) return { id: url.split("/").pop() }
    throw new Error(`unexpected ${url}`)
  })
})

describe("ordinary file uploads", () => {
  it("names a file over the limit before hashing anything, and still uploads the rest", async () => {
    const huge = big("bodycam-1.mp4", MAX_ORDINARY_FILE_BYTES + 1)
    const ok = small("note.txt", "synthetic evidence")
    const seen: string[][] = []
    const result = await uploadOrdinaryFiles("case-1", [huge, ok], undefined, (refused) => {
      seen.push(refused.map((r) => r.name))
      if (seen.length === 1) expect(calls).toEqual([])
    })
    expect(seen[0]).toEqual(["bodycam-1.mp4"])
    expect(huge.slice).not.toHaveBeenCalled()
    expect(result.files).toHaveLength(1)
    expect(result.refused?.[0].reason).toBe(
      "bodycam-1.mp4 is 64.0 GB; one file can be at most 64 GB, so it was not uploaded.",
    )
    expect(result.message).toContain("Uploaded 1 file of 2. Not uploaded: bodycam-1.mp4 is 64.0 GB")
  })

  it("accepts a 1.3 GB file without refusing it", async () => {
    const video = big("bodycam-2.mp4", 1_313_000_000)
    const refusals: unknown[] = []
    // Hashing a fake 1.3 GB file is not the point here: stop at its first read, after the size check passed.
    ;(video.slice as ReturnType<typeof vi.fn>).mockImplementation(() => { throw new Error("read") })
    await uploadOrdinaryFiles("case-1", [video], undefined, (r) => refusals.push(r)).catch(() => null)
    expect(video.slice).toHaveBeenCalled()
    expect(refusals).toEqual([[{ name: "bodycam-2.mp4", reason: "bodycam-2.mp4: read" }]])
  })

  it("keeps uploading after one file fails, and lists the failed one", async () => {
    failName = "b.txt"
    const result = await uploadOrdinaryFiles("case-1", [small("a.txt", "one"), small("b.txt", "two"), small("c.txt", "three")])
    expect(result.files).toHaveLength(2)
    expect(result.refused).toEqual([{ name: "b.txt", reason: "b.txt: Storage is full" }])
    expect(calls.filter((c) => c.endsWith("/complete"))).toHaveLength(2)
  })

  it("fails the upload, naming every file, when none was uploaded", async () => {
    await expect(
      uploadOrdinaryFiles("case-1", [big("x.mp4", MAX_ORDINARY_FILE_BYTES + 1), big("y.mp4", MAX_ORDINARY_FILE_BYTES + 2)]),
    ).rejects.toThrow("None of the 2 files was uploaded. x.mp4 is 64.0 GB")
  })
})
