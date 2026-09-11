import { expect, it } from "vitest"
import { savedIndirectFixture } from "@/test/indirect-workpaper-fixture"
import { readSavedIndirect } from "./saved-indirect"
import { indirectWorkpaperReport } from "./indirect-workpaper-report"
it("reports all saved inputs, checks, references and exact result as escaped text", async () => {
  const f = await savedIndirectFixture()
  const saved = await readSavedIndirect(
    f.link,
    f.entry.links,
    f.caseId,
    async () => f.catalog
  )
  const html = indirectWorkpaperReport(saved, {
    ...f.entry,
    body: '<script>alert("x")</script>',
  })
  for (const value of [
    "Calculated difference: 40.00 GBP",
    "100.00 GBP",
    "60.00 GBP",
    "Opening cash checked: Marked reviewed",
    "Synthetic.pdf",
    "Page 2",
    f.envelope.scenario_sha256,
  ])
    expect(html).toContain(value)
  expect(html).toContain("&lt;script&gt;")
  expect(html).not.toContain("<script>")
  expect(html).toContain("The original files are not included")
  expect(() =>
    indirectWorkpaperReport(saved, { ...f.entry, case_id: f.fileId })
  ).toThrow(/case/)
})
