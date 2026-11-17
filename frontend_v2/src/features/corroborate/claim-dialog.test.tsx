import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { setSwitch } from "@/lib/ui-switches"
import { corroborateAPI, type Claim } from "./api"
import { ClaimButton } from "./ClaimButton"

const chip = (value: string | null, words: string | null) => ({ value, words, confidence: 0.9, read_by: "Read by Loupe · not confirmed" })
const claim: Claim = {
  id: "cl1", status: "draft", sentence: "I was home all evening on the 3rd",
  chips: { who: chip("Kell", "I"), when: chip("2026-05-03 17:00 to 23:59", "all evening on the 3rd"), where: chip(null, null), what: chip("was at home", "was home") },
  missing: ["where"],
}

beforeEach(() => { vi.restoreAllMocks(); setSwitch("corroborate-v2", true) })

function show() {
  render(<MemoryRouter initialEntries={["/cases/c1/theory"]}><Routes>
    <Route path="/cases/c1/theory" element={<ClaimButton caseId="c1" sentence="I was home all evening on the 3rd" source={{ type: "statement_line", id: "s1" }} />} />
    <Route path="/cases/c1/relations/g1" element={<p>result page</p>} />
  </Routes></MemoryRouter>)
}

describe("Corroborate this claim", () => {
  it("shows nothing while the switch is off", () => {
    setSwitch("corroborate-v2", false)
    show()
    expect(screen.queryByText("Corroborate this claim")).toBeNull()
  })
  it("shows the read chips as not confirmed, names a field not stated, and runs only after the person confirms", async () => {
    vi.spyOn(corroborateAPI, "parseClaim").mockResolvedValue({ claim })
    const confirm = vi.spyOn(corroborateAPI, "confirmClaim").mockResolvedValue({ claim: { ...claim, status: "confirmed" } })
    const run = vi.spyOn(corroborateAPI, "run").mockResolvedValue({ group: { id: "g1", member_count: 1, left_out: 0 } })
    show()
    fireEvent.click(screen.getByText("Corroborate this claim"))
    await screen.findByText(/where: not stated, so it is not guessed/)
    expect(screen.getAllByText(/Read by Loupe · not confirmed/).length).toBe(3)
    expect(run).not.toHaveBeenCalled()
    fireEvent.change(screen.getByPlaceholderText("where: not stated"), { target: { value: "home" } })
    fireEvent.click(screen.getByRole("button", { name: "Confirm and corroborate" }))
    await screen.findByText("result page")
    expect(confirm.mock.calls[0][2].where).toMatchObject({ value: "home", read_by: "Edited by you" })
    expect(run.mock.calls[0][1].members).toEqual([expect.objectContaining({ type: "claim", id: "cl1" })])
    expect(run.mock.calls[0][1].question).toMatchObject({ kind: "statement", chips: { claim_id: "cl1" } })
  })
})
