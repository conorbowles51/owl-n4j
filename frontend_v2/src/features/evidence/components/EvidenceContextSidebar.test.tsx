import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { EntityList } from "./EvidenceContextSidebar"
import type { FileEntity } from "../hooks/use-file-entities"

vi.mock("@/features/graph/components/LocationCorrectionInline", () => ({
  LocationCorrectionInline: (props: {
    caseId: string
    nodeKey: string
    sourceView: string
  }) => (
    <div
      data-testid="location-correction"
      data-case-id={props.caseId}
      data-node-key={props.nodeKey}
      data-source-view={props.sourceView}
    />
  ),
}))

describe("EntityList", () => {
  it("wires location entities to the location correction flow", () => {
    const entities: FileEntity[] = [
      {
        id: "entity-1",
        node_key: "loc-1",
        name: "Old Place",
        category: "Location",
        specific_type: "address",
        confidence: 0.6,
        latitude: 1,
        longitude: 2,
        location_formatted: "Old Place",
        geocoding_confidence: "low",
      },
      {
        id: "entity-2",
        node_key: "person-1",
        name: "Jane",
        category: "Person",
        specific_type: "person",
        confidence: 0.9,
      },
    ]

    render(<EntityList entities={entities} caseId="case-1" evidenceId="file-1" />)

    expect(screen.getByText("Old Place")).toBeInTheDocument()
    expect(screen.getByText("Jane")).toBeInTheDocument()
    const correction = screen.getByTestId("location-correction")
    expect(correction).toHaveAttribute("data-case-id", "case-1")
    expect(correction).toHaveAttribute("data-node-key", "loc-1")
    expect(correction).toHaveAttribute("data-source-view", "evidence_panel")
  })
})
