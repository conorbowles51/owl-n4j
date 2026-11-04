import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { patternAPI } from "./api"
import { PaymentPlace } from "./components/PaymentPlace"

const T = "11111111-2222-3333-4444-555555555555"

describe("Attach a place to a payment (04 8.5)", () => {
  afterEach(() => vi.restoreAllMocks())
  it("saves a point and radius with the person's reason through the manual place route", async () => {
    const list = vi.spyOn(patternAPI, "manualPlaces").mockResolvedValueOnce({ total: 0, items: [] }).mockResolvedValueOnce({ total: 1, items: [
      { id: "p", lat: 38.9, lon: -77.03, radius_m: 150, reason: "Receipt names the shop", decision_id: "d", removed_decision_id: null, actor_name: "Jobs", created_at: "x" }] })
    const attach = vi.spyOn(patternAPI, "attachPlace").mockResolvedValue({ place_id: "p", decision_id: "d" })
    render(<PaymentPlace caseId="c" transactionId={T} />)
    fireEvent.click(await screen.findByRole("button", { name: "Attach a place" }))
    fireEvent.change(screen.getByLabelText("Latitude"), { target: { value: "38.9" } })
    fireEvent.change(screen.getByLabelText("Longitude"), { target: { value: "-77.03" } })
    fireEvent.change(screen.getByLabelText("Radius (metres)"), { target: { value: "150" } })
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "Receipt names the shop" } })
    fireEvent.click(screen.getByRole("button", { name: "Save the place" }))
    await waitFor(() => expect(attach).toHaveBeenCalledWith("c", T, 38.9, -77.03, 150, "Receipt names the shop"))
    expect(await screen.findByText(/38\.90000, -77\.03000 within 150 m, attached by Jobs/)).toBeTruthy()
    expect(screen.getByText(/Investigative location, not cell-site opinion/)).toBeTruthy()
    expect(list).toHaveBeenCalledTimes(2)
  })

  it("refuses an off-map point before sending and says why a view-only case refuses", async () => {
    vi.spyOn(patternAPI, "manualPlaces").mockResolvedValue({ total: 0, items: [] })
    const attach = vi.spyOn(patternAPI, "attachPlace").mockRejectedValue(Object.assign(new Error("x"), { status: 403 }))
    render(<PaymentPlace caseId="c" transactionId={T} />)
    fireEvent.click(await screen.findByRole("button", { name: "Attach a place" }))
    fireEvent.change(screen.getByLabelText("Latitude"), { target: { value: "95" } })
    fireEvent.change(screen.getByLabelText("Longitude"), { target: { value: "1" } })
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "r" } })
    expect(screen.getByRole("button", { name: "Save the place" })).toBeDisabled()
    fireEvent.change(screen.getByLabelText("Latitude"), { target: { value: "45" } })
    fireEvent.click(screen.getByRole("button", { name: "Save the place" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("You can view this case but not change it.")
    expect(attach).toHaveBeenCalledTimes(1)
  })
})
