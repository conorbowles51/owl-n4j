import { render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { EntityPopup } from "./EntityPopup"
import type { MapLocation } from "../hooks/use-map-data"

vi.mock("react-map-gl/maplibre", () => ({
  Popup: ({ children }: { children: ReactNode }) => (
    <div data-testid="popup">{children}</div>
  ),
}))

vi.mock("@/features/significant/components/SignificantEntityButton", () => ({
  SignificantEntityButton: () => <div data-testid="significant-entity-button" />,
}))

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

describe("EntityPopup", () => {
  it("wires location correction to the hovered map entity", () => {
    const location: MapLocation = {
      key: "loc-1",
      name: "Old Place",
      type: "location",
      latitude: 51.5,
      longitude: -0.12,
      location_formatted: "Old Place",
      geocoding_confidence: "low",
      manual_correction_history: [],
    }

    render(
      <EntityPopup
        caseId="case-1"
        location={location}
        onClose={vi.fn()}
        onSetProximityAnchor={vi.fn()}
      />
    )

    const correction = screen.getByTestId("location-correction")
    expect(correction).toHaveAttribute("data-case-id", "case-1")
    expect(correction).toHaveAttribute("data-node-key", "loc-1")
    expect(correction).toHaveAttribute("data-source-view", "map_popup")
  })
})
