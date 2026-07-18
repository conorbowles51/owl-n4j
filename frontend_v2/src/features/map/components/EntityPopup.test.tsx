import { render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { EntityPopup, parseGeocodingCandidates } from "./EntityPopup"
import type { MapLocation } from "../hooks/use-map-data"

vi.mock("react-map-gl/maplibre", () => ({
  Popup: ({ children }: { children: ReactNode }) => <div data-testid="map-popup">{children}</div>,
}))

const baseLocation: MapLocation = {
  key: "loc-1",
  name: "Springfield",
  type: "location",
  latitude: 39.9526,
  longitude: -75.1652,
  geocoding_provider: "nominatim",
  geocoding_query: "Springfield",
  geocoding_precision: "city",
  geocoding_confidence: "medium",
}

describe("EntityPopup", () => {
  it("renders geocoder candidate details for ambiguous locations", () => {
    render(
      <EntityPopup
        location={{
          ...baseLocation,
          geocoding_candidates: JSON.stringify([
            {
              latitude: 39.9526,
              longitude: -75.1652,
              formatted_address: "Springfield, Pennsylvania",
              precision: "city",
              confidence: "medium",
            },
            {
              latitude: 39.7817,
              longitude: -89.6501,
              formatted_address: "Springfield, Illinois",
              precision: "city",
              confidence: "medium",
            },
          ]),
        }}
        onClose={vi.fn()}
        onSetProximityAnchor={vi.fn()}
      />
    )

    expect(screen.getByText("Candidates: 2")).toBeInTheDocument()
    expect(screen.getByText("Candidate details")).toBeInTheDocument()
    expect(screen.getByText("1. Springfield, Pennsylvania")).toBeInTheDocument()
    expect(screen.getByText("city / medium / 39.9526, -75.1652")).toBeInTheDocument()
    expect(screen.getByText("2. Springfield, Illinois")).toBeInTheDocument()
    expect(screen.getByText("city / medium / 39.7817, -89.6501")).toBeInTheDocument()
  })
})

describe("parseGeocodingCandidates", () => {
  it("accepts array and JSON-string candidate payloads", () => {
    expect(parseGeocodingCandidates([{ formatted_address: "London, UK", latitude: "51.5", longitude: "-0.12" }])).toEqual([
      {
        latitude: 51.5,
        longitude: -0.12,
        formatted_address: "London, UK",
        precision: undefined,
        confidence: undefined,
      },
    ])
    expect(parseGeocodingCandidates("not json")).toEqual([])
  })
})
