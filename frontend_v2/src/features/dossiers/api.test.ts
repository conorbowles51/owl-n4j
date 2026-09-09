import { beforeEach, describe, expect, it, vi } from "vitest"
import { dossiersAPI } from "./api"

describe("dossiersAPI", () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })
  it("uses bounded server-side list filters", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ dossiers: [], total: 0, limit: 25, offset: 50 }), { status: 200, headers: { "Content-Type": "application/json" } }))
    await dossiersAPI.list({ caseId: "case one", q: "henry", dossierType: "person", linkageState: "linked", limit: 25, offset: 50 })
    const url = String(fetchMock.mock.calls[0][0])
    expect(url).toContain("case_id=case+one")
    expect(url).toContain("dossier_type=person")
    expect(url).toContain("linkage_state=linked")
    expect(url).toContain("limit=25")
    expect(url).toContain("offset=50")
  })
  it("filters and mutates canonical Dossier evidence links", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response(JSON.stringify({ dossiers: [], total: 0, limit: 50, offset: 0 }), { status: 200, headers: { "Content-Type": "application/json" } }))
    await dossiersAPI.list({ caseId: "case-1", linkedEvidenceFileId: "evidence-1" })
    expect(String(fetchMock.mock.calls[0][0])).toContain("linked_evidence_file_id=evidence-1")

    await dossiersAPI.addEvidence("dossier-1", ["evidence-1", "evidence-2"])
    expect(String(fetchMock.mock.calls[1][0])).toBe("/api/dossiers/dossier-1/evidence")
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({ evidence_file_ids: ["evidence-1", "evidence-2"] })

    await dossiersAPI.removeEvidence("dossier-1", "evidence-1")
    expect(String(fetchMock.mock.calls[2][0])).toBe("/api/dossiers/dossier-1/evidence/evidence-1")
    expect(fetchMock.mock.calls[2][1]?.method).toBe("DELETE")
  })
  it("sends non-destructive focal and cover presentation metadata", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({}), { status: 200, headers: { "Content-Type": "application/json" } }))
    await dossiersAPI.updateMedia("dossier-1", "media-1", { is_cover: true, focal_x: .2, focal_y: .8, caption: "Station image" })
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/dossiers/dossier-1/media/media-1")
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ is_cover: true, focal_x: .2, focal_y: .8, caption: "Station image" })
  })
  it("links interviews to multiple source evidence records", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({}), { status: 201, headers: { "Content-Type": "application/json" } }))
    await dossiersAPI.createInterview("dossier-1", { status: "completed", evidence_links: [{ evidence_file_id: "evidence-1" }, { evidence_file_id: "evidence-2", source_anchor: { page: 3 } }] })
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body))
    expect(body.evidence_links).toHaveLength(2)
    expect(body.evidence_links[1].source_anchor).toEqual({ page: 3 })
  })
})
