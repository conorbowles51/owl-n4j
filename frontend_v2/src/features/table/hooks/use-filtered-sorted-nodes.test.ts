import { describe, expect, it } from "vitest"
import { countNodeSources } from "./use-filtered-sorted-nodes"
import type { GraphNode } from "@/types/graph.types"

describe("countNodeSources", () => {
  it("counts distinct source documents stored on graph properties", () => {
    const node = {
      key: "person-1",
      label: "Victoria Blackwood QC",
      type: "person",
      properties: {
        source_files: [
          "registry-supplement.pdf",
          "authorisation.pdf",
          "registry-supplement.pdf",
        ],
      },
    } as GraphNode

    expect(countNodeSources(node)).toBe(2)
  })
})
