import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { PhoneLayers } from "./PhoneLayers"

const phones = [{ id: "a", label: "Phone 1", index: 0 }, { id: "b", label: "Phone 2", index: 1 }, { id: "c", label: "Phone 3", index: 2 }]

describe("PhoneLayers", () => {
  it("lists every phone with its count and says 0 for an empty one", () => {
    render(<PhoneLayers phones={phones} chosen={[]} onChange={() => undefined} counts={{ a: 412, b: 230, c: 0 }} noun="positions" />)
    expect(screen.getByText("412 positions")).toBeTruthy()
    expect(screen.getByText("0 positions")).toBeTruthy()
    expect(screen.getByText("All 3 phones are on.")).toBeTruthy()
  })
  it("switching one off names the rest, Only this keeps one, and the last cannot go off", () => {
    const onChange = vi.fn()
    const { rerender } = render(<PhoneLayers phones={phones} chosen={[]} onChange={onChange} noun="positions" />)
    fireEvent.click(screen.getByLabelText("Phone 2 on"))
    expect(onChange).toHaveBeenLastCalledWith(["a", "c"])
    fireEvent.click(screen.getAllByText("Only this")[2])
    expect(onChange).toHaveBeenLastCalledWith(["c"])
    rerender(<PhoneLayers phones={phones} chosen={["c"]} onChange={onChange} noun="positions" />)
    fireEvent.click(screen.getByLabelText("Phone 3 on"))
    expect(onChange).toHaveBeenLastCalledWith(["c"])
    expect(screen.getByText(/1 of 3 phones are on/)).toBeTruthy()
  })
})
