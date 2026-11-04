import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { NeedsReviewPanel } from "./NeedsReviewPanel"
import type { MapLocation } from "../hooks/use-map-data"

const lookUp = vi.fn()
const confirm = vi.fn()
const fetchSpy = vi.fn()

const flagged = Array.from({ length: 12 }, (_, i) => ({
  key: `loc-${i}`,
  name: `Place ${i}`,
  type: "Location",
  location_raw: `${i} Main St`,
  geocoding_status: i % 2 ? "failed" : "ambiguous",
}))

vi.mock("../hooks/use-map-data", () => ({
  useMapReviewQueue: () => ({ data: flagged }),
}))

const lookupSetting = vi.fn()
vi.mock("@/features/cases/api", () => ({
  casesAPI: { getAddressLookup: (...args: unknown[]) => lookupSetting(...args) },
}))

vi.mock("@/features/graph/api", () => ({
  graphAPI: {
    lookUpFlaggedAddresses: (...args: unknown[]) => lookUp(...args),
    confirmLookedUpLocation: (...args: unknown[]) => confirm(...args),
  },
}))

function renderPanel(locations: MapLocation[] = []) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <NeedsReviewPanel caseId="case-1" locations={locations} />
    </QueryClientProvider>
  )
}

describe("NeedsReviewPanel address lookups", () => {
  beforeEach(() => {
    lookUp.mockReset()
    confirm.mockReset()
    fetchSpy.mockReset()
    vi.stubGlobal("fetch", fetchSpy)
    lookupSetting.mockReset()
    lookupSetting.mockResolvedValue({ mode: "flag", chosen: "flag", default_mode: "auto", words: "", waiting: 0 })
    lookUp.mockImplementation((_case: string, keys: string[]) =>
      Promise.resolve({
        results: keys.map((key) => ({ key, outcome: "no_match", message: "No match found for this address." })),
        counts: { no_match: keys.length },
      })
    )
  })

  it("sends nothing until a person clicks", () => {
    renderPanel()
    expect(screen.getByText(/Nothing is looked up until you ask/)).toBeInTheDocument()
    expect(screen.getAllByRole("button", { name: /^Look up$/ })).toHaveLength(12)
    expect(lookUp).not.toHaveBeenCalled()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("sends exactly the clicked address, once, and says what it found", async () => {
    renderPanel()
    fireEvent.click(screen.getAllByRole("button", { name: /^Look up$/ })[3])
    await screen.findByText("No match found for this address.")
    expect(lookUp).toHaveBeenCalledTimes(1)
    expect(lookUp).toHaveBeenCalledWith("case-1", ["loc-3"])
  })

  it("Look up all asks first, names the outside service, then sends every flagged address in small batches", async () => {
    renderPanel()
    fireEvent.click(screen.getByRole("button", { name: "Look up all 12" }))
    expect(lookUp).not.toHaveBeenCalled()
    expect(screen.getByText(/OpenStreetMap address service \(outside this server\)/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Send 12" }))
    await screen.findByText("Looked up 12: 0 placed (not confirmed), 12 no match.")
    expect(lookUp).toHaveBeenCalledTimes(2)
    expect(lookUp.mock.calls[0][1]).toHaveLength(10)
    expect(lookUp.mock.calls[1][1]).toHaveLength(2)
    const sent = lookUp.mock.calls.flatMap((call) => call[1] as string[])
    expect(new Set(sent).size).toBe(12)
  })

  it("says when the case looks addresses up automatically", async () => {
    lookupSetting.mockResolvedValue({ mode: "auto", chosen: null, default_mode: "auto", words: "", waiting: 4 })
    renderPanel()
    await screen.findByText(/looked up automatically \(4 waiting, one a second\)/)
    expect(lookUp).not.toHaveBeenCalled()
  })

  it("Cancel sends nothing", () => {
    renderPanel()
    fireEvent.click(screen.getByRole("button", { name: "Look up all 12" }))
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
    expect(lookUp).not.toHaveBeenCalled()
  })

  it("shows a looked-up pin as not confirmed until a person confirms it", async () => {
    confirm.mockResolvedValue({ success: true, confirmed_at: "2026-11-04T02:00:00Z" })
    const pin = {
      key: "pin-1",
      name: "Warehouse",
      type: "location",
      latitude: 38.9,
      longitude: -77.0,
      location_raw: "1 Dock Rd",
      geocoding_status: "looked_up",
      geocoding_confidence: "high",
      geocoding_requested_by_name: "Ann Investigator",
      manual_correction_history: [],
    } as unknown as MapLocation
    renderPanel([pin])
    expect(screen.getByText(/Placed by address lookup · not confirmed/)).toBeInTheDocument()
    expect(screen.getByText(/Asked by Ann Investigator/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /Confirm/ }))
    await waitFor(() => expect(confirm).toHaveBeenCalledWith("pin-1", "case-1"))
  })
})
