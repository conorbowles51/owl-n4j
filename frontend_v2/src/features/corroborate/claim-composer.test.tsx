import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { setSwitch } from "@/lib/ui-switches"
import { claimAPI, corroborateAPI, type ParsedClaim } from "./api"
import { openClaimComposer, toZoneInput, fromZoneInput } from "./claim-composer"
import { CorroborateTray } from "./CorroborateTray"

const READ = "Read by Loupe · not confirmed"
const parsed: ParsedClaim = {
  id: "cl1", status: "draft", sentence: "I was home all evening on the 3rd.", zone: "America/New_York", read_by: READ, missing: ["where"],
  people: [{ key: "person:a", label: "Ann Arden" }, { key: "person:b", label: "Bob Brook" }],
  chips: {
    who: { status: "read", value: [{ key: "person:a", label: "Ann Arden", words: "I" }], words: "I", confidence: "high", source: "rule", read_by: READ },
    when: { status: "read", value: { start: "2025-01-03T23:00:00+00:00", end: "2025-01-04T05:00:00+00:00", zone: "America/New_York", label: "x" }, words: "the 3rd all evening", confidence: "medium", source: "rule", read_by: READ, note: "resolved against the statement date" },
    where: { status: "not_located", value: { name: "home of Ann Arden", located: false }, words: "home", confidence: "low", source: "rule", read_by: READ, note: "“home” is home of Ann Arden, but Loupe has no position for it" },
    what: { status: "read", value: { action: "presence", negated: false, with: [] }, words: "was", confidence: "medium", source: "rule", read_by: READ },
  },
}

function wrap() {
  return render(<MemoryRouter initialEntries={["/cases/c1/ledger"]}><Routes>
    <Route path="/cases/:id/ledger" element={<CorroborateTray />} /><Route path="/cases/c1/corroborate" element={<p>result page</p>} />
  </Routes></MemoryRouter>)
}
beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); setSwitch("corroborate-v2", true) })

describe("Corroborate this claim", () => {
  it("shows each chip as Read by Loupe with its words, says what is missing, and confirms only on the button", async () => {
    vi.spyOn(claimAPI, "parse").mockResolvedValue({ claim: parsed })
    const confirm = vi.spyOn(claimAPI, "confirm").mockResolvedValue({ claim: { id: "cl1", status: "confirmed" } })
    const run = vi.spyOn(corroborateAPI, "run").mockResolvedValue({ group: { id: "g9", member_count: 1, left_out: 0 } })
    wrap()
    openClaimComposer({ text: parsed.sentence, statementDate: "2025-01-10" })
    await screen.findByLabelText("Latitude")
    expect(screen.getAllByText(/Read by Loupe · not confirmed/).length).toBe(3)
    expect(screen.getByText(/no position for it/)).toBeTruthy()
    expect(screen.getByText(/from “the 3rd all evening”/)).toBeTruthy()
    expect(claimAPI.parse).toHaveBeenCalledWith("c1", expect.objectContaining({ text: parsed.sentence, statement_date: "2025-01-10" }))
    expect(confirm).not.toHaveBeenCalled()
    expect(run).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("button", { name: "Confirm and corroborate" }))
    await waitFor(() => expect(run).toHaveBeenCalled())
    const sent = confirm.mock.calls[0][2]
    expect(sent.where).toBeNull()
    expect(sent.where_text).toMatch(/no position/)
    expect(run.mock.calls[0][1].members).toEqual([expect.objectContaining({ type: "claim", id: "cl1" })])
    expect(run.mock.calls[0][1].question.chips).toEqual({ claim_id: "cl1" })
    await screen.findByText("result page")
  })

  it("sends a position the person types as the place", async () => {
    vi.spyOn(claimAPI, "parse").mockResolvedValue({ claim: parsed })
    const confirm = vi.spyOn(claimAPI, "confirm").mockResolvedValue({ claim: { id: "cl1", status: "confirmed" } })
    vi.spyOn(corroborateAPI, "run").mockResolvedValue({ group: { id: "g9", member_count: 1, left_out: 0 } })
    wrap()
    openClaimComposer({ text: parsed.sentence })
    fireEvent.change(await screen.findByLabelText("Latitude"), { target: { value: "51.5" } })
    fireEvent.change(screen.getByLabelText("Longitude"), { target: { value: "-0.1" } })
    fireEvent.click(screen.getByRole("button", { name: "Confirm and corroborate" }))
    await waitFor(() => expect(confirm).toHaveBeenCalled())
    expect(confirm.mock.calls[0][2].where).toMatchObject({ lat: 51.5, lon: -0.1, radius_m: 150 })
  })

  it("keeps the case's wall-clock when it converts a time", () => {
    const iso = fromZoneInput("2025-07-03T19:00", "America/New_York")
    expect(iso).toBe("2025-07-03T23:00:00.000Z")
    expect(toZoneInput(iso, "America/New_York")).toBe("2025-07-03T19:00")
    expect(fromZoneInput("2025-01-03T19:00", "America/New_York")).toBe("2025-01-04T00:00:00.000Z")
  })
})
