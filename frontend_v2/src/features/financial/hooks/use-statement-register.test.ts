import { describe, expect, it } from "vitest"
import { mergeSavedImports } from "./use-statement-register"

type Imports = Parameters<typeof mergeSavedImports>[0]
type Grouped = Parameters<typeof mergeSavedImports>[1]

// The merge as it was written before the index (every file compared with every saved entry).
function filterMerge(importsData: Imports, grouped: Grouped) {
  return {
    ...importsData,
    files: grouped.flatMap((file) => {
      const ids = new Set(file.readingVersions.map((version) => version.id))
      const entries = importsData.files.filter((item) => ids.has(item.evidence_file_id))
      if (!entries.length) return []
      const latest = entries.find((entry) => entry.evidence_file_id === file.id)
      return [{ ids: entries.map((entry) => entry.evidence_file_id), latest: latest?.pending_periods,
        same: [...new Set(entries.flatMap((entry) => entry.same_pdf_saved_file_ids))].filter((id) => !ids.has(id)),
        current: entries.reduce((sum, entry) => sum + entry.current_transactions, 0),
        periods: entries.flatMap((entry) => entry.periods).filter((p) => p.source_status === "admitted") }]
    }),
  }
}

const entry = (id: string, n: number, same: string[] = []) => ({
  evidence_file_id: id, same_pdf_saved_file_ids: same, current_transactions: n, incomplete_count: 0,
  awaiting_reconciliation_count: 0, incomplete_sources: [], receipt_review_count: 0, wire_review_count: 0,
  periods: [{ source_status: n % 2 ? "admitted" : "superseded", n }], pending_periods: n,
})

describe("merging saved imports across reading versions", () => {
  it("gives each file the same entries, in the answer's order, as comparing every file with every entry", () => {
    const files = [entry("b", 1, ["x", "a"]), entry("a", 2), entry("c", 3), entry("b", 5, ["y"]), entry("z", 7), entry("a", 9)]
    const importsData = { case_id: "case", files } as unknown as Imports
    const grouped = [
      { id: "a", readingVersions: [{ id: "a" }, { id: "b" }] },
      { id: "c", readingVersions: [{ id: "c" }, { id: "c" }] },
      { id: "q", readingVersions: [{ id: "q" }] },
      { id: "z", readingVersions: [{ id: "y" }, { id: "z" }] },
    ] as unknown as Grouped
    const merged = mergeSavedImports(importsData, grouped)
    const expected = filterMerge(importsData, grouped)
    expect(merged.files.map((file) => ({
      ids: files.filter((item) => grouped.find((g) => g.id === file.evidence_file_id)!.readingVersions
        .some((v) => v.id === item.evidence_file_id)).map((item) => item.evidence_file_id),
      latest: file.pending_periods, same: file.same_pdf_saved_file_ids, current: file.current_transactions,
      periods: file.periods,
    }))).toEqual(expected.files)
    expect(merged.files.map((file) => file.evidence_file_id)).toEqual(["a", "c", "z"])
    expect(merged.files[0].current_transactions).toBe(1 + 2 + 5 + 9)
    expect(merged.files[0].pending_periods).toBe(2) // the first saved entry of the file itself
  })
})
