import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { patternAPI } from "./api"
import { PaymentPlace } from "./components/PaymentPlace"

const T = "11111111-2222-3333-4444-555555555555"

describe("Attach a place to a payment (04 8.5)", () => {
  afterEach(() => vi.restoreAllMocks())
  beforeEach(() => { vi.spyOn(patternAPI, "placeSuggestions").mockResolvedValue({ enabled: true, reason: "r", total: 0, returned: 0, candidates: [] }) })
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
    await waitFor(() => expect(attach).toHaveBeenCalledWith("c", T, 38.9, -77.03, 150, "Receipt names the shop", null))
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

  const town = { name: "Battleboro", lat: 36.05, lon: -77.75, country_code: "US", country: "United States", admin1: "North Carolina", population: 2000, geonameid: 7, matched: "battleboro NC" }
  const offered = { enabled: true, reason: "r", total: 1, returned: 1, candidates: [town], label: "Suggested, not confirmed", words: "Nothing is saved until a person attaches a place.", attribution: "Place names: GeoNames" }

  it("shows a town from the payment's text as a suggestion, and saves nothing until a person writes why and saves", async () => {
    vi.spyOn(patternAPI, "manualPlaces").mockResolvedValue({ total: 0, items: [] })
    vi.spyOn(patternAPI, "placeSuggestions").mockResolvedValue(offered)
    const attach = vi.spyOn(patternAPI, "attachPlace").mockResolvedValue({ place_id: "p", decision_id: "d" })
    render(<PaymentPlace caseId="c" transactionId={T} />)
    fireEvent.click(await screen.findByRole("button", { name: "Attach a place" }))
    expect(await screen.findByText("Suggested, not confirmed")).toBeTruthy()
    expect(screen.getByText("Battleboro, North Carolina, United States")).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "Use this town" }))
    expect(screen.getByLabelText("Latitude")).toHaveValue("36.05")
    expect(screen.getByLabelText("Radius (metres)")).toHaveValue("5000")
    expect(attach).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "Save the place" })).toBeDisabled()   // a person's reason is still needed
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "The card line names the town" } })
    fireEvent.click(screen.getByRole("button", { name: "Save the place" }))
    await waitFor(() => expect(attach).toHaveBeenCalledWith("c", T, 36.05, -77.75, 5000, "The card line names the town", town))
  })

  it("a point typed over a suggestion is the person's own, with no suggestion kept", async () => {
    vi.spyOn(patternAPI, "manualPlaces").mockResolvedValue({ total: 0, items: [] })
    vi.spyOn(patternAPI, "placeSuggestions").mockResolvedValue(offered)
    const attach = vi.spyOn(patternAPI, "attachPlace").mockResolvedValue({ place_id: "p", decision_id: "d" })
    render(<PaymentPlace caseId="c" transactionId={T} />)
    fireEvent.click(await screen.findByRole("button", { name: "Attach a place" }))
    fireEvent.click(await screen.findByRole("button", { name: "Use this town" }))
    fireEvent.change(screen.getByLabelText("Latitude"), { target: { value: "36.1" } })
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "Receipt" } })
    fireEvent.click(screen.getByRole("button", { name: "Save the place" }))
    await waitFor(() => expect(attach).toHaveBeenCalledWith("c", T, 36.1, -77.75, 5000, "Receipt", null))
  })

  it("says so when suggestions are off, and shows nothing when the text names no town", async () => {
    vi.spyOn(patternAPI, "manualPlaces").mockResolvedValue({ total: 0, items: [] })
    const sug = vi.spyOn(patternAPI, "placeSuggestions").mockResolvedValue({ enabled: false, reason: "Suggestions are off: not installed.", total: 0, returned: 0, candidates: [] })
    render(<PaymentPlace caseId="c" transactionId={T} />)
    fireEvent.click(await screen.findByRole("button", { name: "Attach a place" }))
    expect(await screen.findByText("Suggestions are off: not installed.")).toBeTruthy()
    expect(sug).toHaveBeenCalledTimes(1)
  })
})
