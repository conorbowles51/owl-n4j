import { afterEach, describe, expect, it, vi } from "vitest"

const fetchAPI = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", () => ({ fetchAPI }))

import { undoCollect } from "./collect.api"

const dossier = { kind: "dossier" as const, id: "d1", label: "Synthetic dossier" }
const note = { kind: "note" as const, id: "n1", label: "Synthetic note" }

describe("Undo of Add to… (07 J-12; review of 03-3)", () => {
  afterEach(() => fetchAPI.mockReset())

  it("says how many are removed so far: an undo of hundreds takes minutes", async () => {
    fetchAPI.mockResolvedValue({ version: 2 })
    const seen: string[] = []
    await undoCollect("c1", dossier, { added: 2, skipped: 0, refused: 0, linkIds: ["l1", "l2"] }, (done, all) => seen.push(`${done}/${all}`))
    expect(seen).toEqual(["1/2", "2/2"])
  })

  it("removes exactly the links the add created", async () => {
    fetchAPI.mockResolvedValue({})
    expect(await undoCollect("c1", dossier, { added: 2, skipped: 5, refused: 0, linkIds: ["l1", "l2"] })).toBe(2)
    expect(fetchAPI.mock.calls.map((c) => c[0])).toEqual(["/api/dossiers/d1/links/l1", "/api/dossiers/d1/links/l2"])
  })

  it("names each entry version it expects, and says how many were removed when it stops", async () => {
    fetchAPI.mockResolvedValueOnce({ version: 8 }).mockRejectedValueOnce(new Error("This note was changed by someone else"))
    await expect(undoCollect("c1", note, { added: 2, skipped: 0, refused: 0, linkIds: ["l1", "l2"], version: 7 })).rejects.toThrow(
      "Undo stopped after removing 1 of 2: This note was changed by someone else",
    )
    expect(fetchAPI.mock.calls[0][0]).toContain("expected_version=7")
    expect(fetchAPI.mock.calls[1][0]).toContain("expected_version=8")
  })
})
