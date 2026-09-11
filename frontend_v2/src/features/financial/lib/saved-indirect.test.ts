import { expect, it, vi } from "vitest"
import { savedIndirectFixture } from "@/test/indirect-workpaper-fixture"
import { readSavedIndirect } from "./saved-indirect"
it("reopens historical definitions without recalculating or fetching current methods", async () => {
  const f = await savedIndirectFixture()
  const load = vi.fn()
  const result = await readSavedIndirect(f.link, f.entry.links, f.caseId, load)
  expect(result.review.envelope.scenario_json).toBe(f.envelope.scenario_json)
  expect(result.review.value.difference_minor).toBe("4000")
  expect(load).not.toHaveBeenCalled()
})
it("opens older notes against current methods and refuses incompatible definitions", async () => {
  const f = await savedIndirectFixture(false)
  const load = vi.fn().mockResolvedValue(f.catalog)
  expect(
    (await readSavedIndirect(f.link, [f.link], f.caseId, load)).review.value
      .inputs
  ).toEqual(f.inputs)
  expect(load).toHaveBeenCalledOnce()
  await expect(
    readSavedIndirect(f.link, [f.link], f.caseId, async () => ({
      ...f.catalog,
      requirements: [],
    }))
  ).rejects.toThrow(/fields/)
  await expect(
    readSavedIndirect(f.link, [f.link], f.caseId, async () => ({
      ...f.catalog,
      methods: [],
    }))
  ).rejects.toThrow()
})
it("rejects another case, missing sources, changed anchors and unrelated evidence", async () => {
  const f = await savedIndirectFixture()
  const read = (link = f.link, links = [link], caseId = f.caseId) =>
    readSavedIndirect(link, links, caseId, async () => f.catalog)
  await expect(read(f.link, [f.link], f.fileId)).rejects.toThrow(/case/)
  await expect(read(f.link, [])).rejects.toThrow(/sources/)
  await expect(
    read({ ...f.link, source_anchor: { workpaper_sha256: "0".repeat(64) } })
  ).rejects.toThrow(/sources/)
  await expect(read({ ...f.link, target_id: f.caseId })).rejects.toThrow(
    /sources/
  )
  await expect(
    read(f.link, [f.link, { ...f.link, target_id: f.caseId }])
  ).rejects.toThrow(/sources/)
  await expect(read({ ...f.link, target_type: "entry" })).rejects.toThrow(
    /sources/
  )
})
it("checks bytes before opening and does not accept a damaged catalog as a legacy record", async () => {
  const f = await savedIndirectFixture()
  const read = (metadata: Record<string, unknown>) =>
    readSavedIndirect({ ...f.link, metadata }, [f.link], f.caseId, vi.fn())
  await expect(
    read({
      ...f.link.metadata,
      envelope: {
        ...f.envelope,
        scenario_json: f.envelope.scenario_json + " ",
      },
    })
  ).rejects.toThrow(/integrity/)
  await expect(
    read({
      ...f.link.metadata,
      envelope: { ...f.envelope, scenario_json: "x".repeat(1024 * 1024 + 1) },
    })
  ).rejects.toThrow(/large/)
  await expect(read({ ...f.link.metadata, catalog: {} })).rejects.toThrow()
})
