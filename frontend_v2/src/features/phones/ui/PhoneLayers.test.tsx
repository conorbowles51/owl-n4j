import { fireEvent, render, screen, within } from "@testing-library/react"
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

  it("beside each label names the owner for a few phones", () => {
    render(<PhoneLayers phones={[{ id: "a", label: "C1", index: 0, owner: "Lena Marsh" }, { id: "b", label: "C2", index: 1 }]} chosen={[]} onChange={() => undefined} noun="positions" />)
    expect(screen.getByText("(Lena Marsh)")).toBeTruthy()
  })

  it("for many phones groups by owner, searches by phone or owner, and still switches one on its own", () => {
    const many = Array.from({ length: 8 }, (_, i) => ({ id: `p${i}`, label: `C${i + 1}`, index: i, owner: i < 3 ? "Lena Marsh" : i < 5 ? "Travis Kell" : null }))
    const onChange = vi.fn()
    render(<PhoneLayers phones={many} chosen={[]} onChange={onChange} counts={null} noun="positions" />)
    expect(screen.getByRole("group", { name: "Lena Marsh" })).toBeTruthy()
    expect(within(screen.getByRole("group", { name: "Lena Marsh" })).getAllByRole("checkbox")).toHaveLength(3)
    expect(screen.getByRole("group", { name: "No owner named" })).toBeTruthy()
    fireEvent.change(screen.getByLabelText("Find a phone or owner"), { target: { value: "kell" } })
    expect(screen.queryByRole("group", { name: "Lena Marsh" })).toBeNull()
    expect(within(screen.getByRole("group", { name: "Travis Kell" })).getAllByRole("checkbox")).toHaveLength(2)
    fireEvent.click(screen.getByLabelText("C5 on"))
    expect(onChange).toHaveBeenLastCalledWith(["p0", "p1", "p2", "p3", "p5", "p6", "p7"])
    fireEvent.change(screen.getByLabelText("Find a phone or owner"), { target: { value: "zzz" } })
    expect(screen.getByText(/No phone or owner matches "zzz"/)).toBeTruthy()
  })
})
