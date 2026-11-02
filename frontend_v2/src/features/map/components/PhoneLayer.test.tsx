import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"
import { PhoneLayerPanel } from "./PhoneLayer"

const summary = {
  case_id: "c", positioned: 2, total: 6, by_source: { device_location: 2 }, bbox: [-74, 40, -73, 41],
  not_positionable: [{ reason: "Cell tower records without a position: the production gives tower identifiers only", model_type: "CellTower", count: 4, phones: 1 }],
}
const point = (uid: string, accuracy: number | null) => ({
  type: "point" as const, point_uid: uid, record_uid: `r-${uid}`, extraction_id: "e", phone_label: "C1", lat: 40, lon: -74,
  accuracy_m: accuracy, accuracy_words: accuracy === null ? "Accuracy not recorded" : `Within ${accuracy} m`, source_words: "Location services",
  affiliation: null, instant: "2023-03-14T12:00:00Z", time: { full: "Tuesday, March 14, 2023 8:00:00 AM" }, model_type: "Location", flags: [], deleted_state: null,
})

describe("Map phone layer (03 13.3, G-2)", () => {
  it("states what is shown and what cannot be placed, and each point's accuracy", () => {
    render(
      <MemoryRouter>
        <PhoneLayerPanel caseId="c" summary={summary} points={{ case_id: "c", total: 2, clustered: false, limits: [], items: [point("a", null), point("b", 25)] }} />
      </MemoryRouter>,
    )
    expect(screen.getByText(/Showing 2 of 6 positioned records\./)).toBeInTheDocument()
    expect(screen.getByText(/4 cannot be placed/)).toBeInTheDocument()
    expect(screen.getByText("Accuracy not recorded")).toBeInTheDocument()
    expect(screen.getByText("Within 25 m")).toBeInTheDocument()
    expect(screen.getAllByRole("link", { name: "Open the record behind this" })[0]).toHaveAttribute("href", "/cases/c/records/r-a")
    fireEvent.click(screen.getByRole("button", { name: "why" }))
    expect(screen.getByText(/never sent to a lookup service/)).toBeInTheDocument()
  })

  it("shows the clustering limit when the view holds too many points (G-1)", () => {
    render(
      <MemoryRouter>
        <PhoneLayerPanel caseId="c" summary={summary} points={{ case_id: "c", total: 12431, clustered: true, items: [], limits: [{ message: "12,431 positions in this view are grouped into 40 clusters; zoom in to see each one." }] }} />
      </MemoryRouter>,
    )
    expect(screen.getByRole("alert")).toHaveTextContent("12,431 positions in this view are grouped into 40 clusters")
  })
})
