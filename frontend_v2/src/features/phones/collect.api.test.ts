import { afterEach, describe, expect, it, vi } from "vitest"

const fetchAPI = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", () => ({ fetchAPI }))

import { undoCollect } from "./collect.api"

const dossier = { kind: "dossier" as const, id: "d1", label: "Synthetic dossier" }
const note = { kind: "note" as const, id: "n1", label: "Synthetic note" }

describe("Undo of Add to… (07 J-12; review of 03-3)", () => {
  afterEach(() => fetchAPI.mockReset())

  it("removes exactly the links the add created, in one call", async () => {
    fetchAPI.mockResolvedValue({})
    const seen: string[] = []
    expect(await undoCollect("c1", dossier, { added: 2, skipped: 5, refused: 0, linkIds: ["l1", "l2"] }, (done, all) => seen.push(`${done}/${all}`))).toBe(2)
    expect(fetchAPI.mock.calls).toEqual([["/api/dossiers/d1/links:remove", { method: "POST", body: { link_ids: ["l1", "l2"] } }]])
    expect(seen).toEqual(["2/2"])
  })

  it("sends what one call cannot take in parts, naming each entry version it expects, and says how many were removed when it stops", async () => {
    fetchAPI.mockResolvedValueOnce({ version: 8 }).mockRejectedValueOnce(new Error("This note was changed by someone else"))
    const linkIds = Array.from({ length: 5001 }, (_, i) => `l${i}`)
    await expect(undoCollect("c1", note, { added: 5001, skipped: 0, refused: 0, linkIds, version: 7 })).rejects.toThrow(
      "Undo stopped after removing 5,000 of 5,001: This note was changed by someone else",
    )
    expect(fetchAPI.mock.calls[0][0]).toBe("/api/workspace/c1/entries/n1/links:remove")
    expect(fetchAPI.mock.calls[0][1].body.expected_version).toBe(7)
    expect(fetchAPI.mock.calls[0][1].body.link_ids).toHaveLength(5000)
    expect(fetchAPI.mock.calls[1][1].body).toEqual({ link_ids: ["l5000"], expected_version: 8 })
  })
})
