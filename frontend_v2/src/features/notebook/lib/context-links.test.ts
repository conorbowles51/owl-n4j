import { describe, expect, it } from "vitest"
import { buildNotebookContextLinks } from "./context-links"

describe("buildNotebookContextLinks", () => {
  it("turns the current graph and evidence selection into readable links", () => {
    expect(
      buildNotebookContextLinks({
        selectedNodeKeys: ["person-1"],
        selectedNodeDetails: [
          {
            key: "person-1",
            label: "Henry Walsh",
            type: "person",
            properties: {},
            connections: [],
            sources: [],
          },
        ],
        selectedFileIds: ["file-1"],
        evidenceFiles: [
          { id: "file-1", original_filename: "Transfer ledger.pdf" },
        ],
      })
    ).toEqual([
      {
        target_type: "entity",
        target_id: "person-1",
        target_label: "Henry Walsh",
        metadata: { source: "current_selection" },
      },
      {
        target_type: "evidence",
        target_id: "file-1",
        target_label: "Transfer ledger.pdf",
        metadata: { source: "current_selection" },
      },
    ])
  })

  it("keeps a stable identifier as a fallback when labels have not loaded", () => {
    expect(
      buildNotebookContextLinks({
        selectedNodeKeys: ["organisation-2"],
        selectedNodeDetails: [undefined],
        selectedFileIds: ["file-2"],
        evidenceFiles: [],
      })
    ).toEqual([
      expect.objectContaining({ target_label: "organisation-2" }),
      expect.objectContaining({ target_label: "file-2" }),
    ])
  })
})
