import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { describe, expect, it } from "vitest"
import { NearMessageNote } from "./NearMessageNote"

/** Show on Map from a message (03 section 3.6 item 7): the note's wording and its links. Synthetic values only. */
function Where() {
  const l = useLocation()
  return <p data-testid="where">{l.pathname + l.search}</p>
}

const empty = {
  record_uid: "r-1", extraction_id: "e1", instant: "2023-03-14T15:00:00Z", window_minutes: 60, within: 0,
  from_instant: "2023-03-14T14:00:00Z", to_instant: "2023-03-14T16:00:00Z", bbox: null,
  nearest: { point_uid: "p1", lat: 38.9, lon: -77.03, instant: "2023-03-14T11:48:00Z", gap_seconds: -11520, gap_words: "3 h 12 min earlier" },
  words: "No positioned records within 1 hour of this message. The nearest is 3 h 12 min earlier.",
}

function show(near: typeof empty) {
  render(
    <MemoryRouter initialEntries={["/cases/c1/map?phone_near=r-1"]}>
      <Routes>
        <Route path="*" element={<><NearMessageNote loading={false} failed={false} near={near} /><Where /></>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe("Show on Map from a message", () => {
  it("with nothing in the hour, says how far the nearest is and Show it centres on it", () => {
    show(empty)
    expect(screen.getByRole("status")).toHaveTextContent(
      "No positioned records within 1 hour of this message. The nearest is 3 h 12 min earlier. Show it.",
    )
    fireEvent.click(screen.getByRole("link", { name: "Show it" }))
    expect(screen.getByTestId("where")).toHaveTextContent("/cases/c1/map?phone_point=-77.03,38.9")
  })

  it("with positions in the hour, says how many are drawn and offers every position", () => {
    show({ ...empty, within: 2, nearest: null, bbox: [-77.1, 38.85, -77, 38.95], words: "2 positioned records on the same phone within 1 hour of this message." } as never)
    expect(screen.getByRole("status")).toHaveTextContent("2 positioned records on the same phone within 1 hour of this message. Only those are drawn.")
    fireEvent.click(screen.getByRole("link", { name: "Show every position" }))
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/cases\/c1\/map$/)
  })
})
