import { expect, it } from "vitest"
import { compareArtifacts } from "./artifact-compare"
import { latestArtifactVersion } from "./artifact-data"
import type { AgentArtifact } from "./types"

const before: AgentArtifact = { id: "v1", title: "Initial title", type: "report", metadata: { deliverable_id: "report", revision: 1 }, data: { sections: [
  { id: "parent", heading: "Scope", content: "Unchanged scope", children: [{ id: "nested", heading: "Analysis", content: "Before text" }, { id: "removed", heading: "Removed section", content: "Old" }] },
] } }
const after: AgentArtifact = { ...before, id: "v2", title: "Revised title", metadata: { deliverable_id: "report", revision: 2 }, data: { sections: [
  { id: "parent", heading: "Scope", content: "Unchanged scope", children: [{ id: "nested", heading: "Expanded analysis", content: "After text" }, { id: "added", heading: "New section", content: "New" }] },
] } }

it("matches nested sections by stable ID and separates additions, removals and changed text", () => {
  const changes = compareArtifacts(before, after)
  expect(changes.titleChanged).toBe(true)
  expect(changes.sectionChanges.map((change) => [change.key, change.kind])).toEqual([["id:nested", "Changed"], ["id:added", "Added"], ["id:removed", "Removed"]])
  expect(changes.sectionChanges[0].before?.content).toBe("Before text")
  expect(changes.sectionChanges[0].after?.content).toBe("After text")
})

it("reports dataset size, column labels/order and cell changes, including equal-sized data", () => {
  const previous: AgentArtifact = { ...before, type: "workbook", data: { sheets: [{ name: "Evidence", columns: ["source", "amount"], rows: [{ source: "A", amount: 1 }] }] } }
  const current: AgentArtifact = { ...previous, data: { sheets: [{ name: "Evidence", columns: [{ key: "amount", label: "Revised amount" }, { key: "source", label: "Source" }, { key: "note", label: "Review note" }], rows: [{ source: "A", amount: 2, note: "Reviewed" }, { source: "B", amount: 3 }] }] } }
  const [change] = compareArtifacts(previous, current).datasetChanges
  expect(change.before?.rows).toHaveLength(1)
  expect(change.after?.rows).toHaveLength(2)
  expect(change.rowsChanged).toBe(true)
  expect(change.columnsChanged).toBe(true)
  expect(change.after?.columns.map((c) => c.label)).toEqual(["Revised amount", "Source", "Review note"])
  expect(compareArtifacts(previous, { ...previous, data: { sheets: [{ name: "Evidence", columns: ["source", "amount"], rows: [{ source: "A", amount: 2 }] }] } }).datasetChanges[0].rowsChanged).toBe(true)
})

it("defaults to the newest revision of the first family without selecting another deliverable", () => {
  expect(latestArtifactVersion([before, { ...before, id: "unrelated", metadata: { revision: 9 } }, after])?.id).toBe("v2")
  expect(latestArtifactVersion([])).toBeNull()
  expect(compareArtifacts(before, { ...before, id: "new-version" }).contentChanged).toBe(false)
})
