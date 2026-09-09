import { describe, expect, it } from "vitest"
import { invalidMoveReason, type MoveSource } from "./move-targets"
import { getDisplayStatus } from "./display-status"

const folders = [
  { id: "parent", parent_id: null, name: "Parent" },
  { id: "child", parent_id: "parent", name: "Child" },
  { id: "target", parent_id: null, name: "Target" },
  { id: "conflict", parent_id: "target", name: "Parent" },
]
describe("evidence destinations", () => {
  it("rejects cycles, current destinations, missing destinations and folder name conflicts", () => {
    const source: MoveSource = { kind: "folder", ...folders[0] }
    for (const destination of [null, "parent", "child", "target", "missing"])
      expect(invalidMoveReason(source, destination, folders)).toBeTruthy()
    expect(
      invalidMoveReason(
        source,
        "target",
        folders.filter((folder) => folder.id !== "conflict")
      )
    ).toBeNull()
  })
  it("allows root and mixed-location batches with no-op members", () => {
    const source: MoveSource = {
      kind: "files",
      files: [
        { id: "a", folder_id: "child" },
        { id: "b", folder_id: "target" },
      ],
    }
    expect(invalidMoveReason(source, "target", folders)).toBeNull()
    expect(invalidMoveReason(source, null, folders)).toBeNull()
    expect(
      invalidMoveReason(
        { kind: "files", files: [source.files[1]] },
        "target",
        folders
      )
    ).toBeTruthy()
  })
  it("ignores historical stale flags", () => {
    const file = { status: "processed" as const, processing_stale: true }
    expect(getDisplayStatus(file)).toBe("processed")
  })
})
