import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { MappingBacklog } from "./PhoneSummaryPage"

afterEach(cleanup)

describe("MappingBacklog (02 3.4: the backlog shown in the coverage map)", () => {
  it("lists every flag waiting for a mapping with the total", () => {
    render(
      <MappingBacklog
        backlog={{
          total: 2,
          items: [
            { flag_id: 1, flag_kind: "new_type", subject: { type: "ZzType" } },
            { flag_id: 2, flag_kind: "new_field", subject: { type: "Call", field: "ZzField", value_type: "String" } },
          ],
        }}
      />
    )
    expect(screen.getByText(/Waiting for a mapping \(2\)/)).toBeTruthy()
    expect(screen.getByText("New record type: ZzType")).toBeTruthy()
    expect(screen.getByText("New field: Call · ZzField (String)")).toBeTruthy()
  })

  it("says so when nothing is waiting, and shows nothing for an older server", () => {
    const { container, rerender } = render(<MappingBacklog backlog={{ total: 0, items: [] }} />)
    expect(screen.getByText("Nothing on this phone is waiting for a mapping.")).toBeTruthy()
    rerender(<MappingBacklog backlog={undefined} />)
    expect(container.textContent).toBe("")
  })
})
