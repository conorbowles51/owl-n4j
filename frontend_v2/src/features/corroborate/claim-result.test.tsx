import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { ClaimResult } from "./ClaimResult"
import type { Corroboration } from "./result-types"

const base = { schema: "s", question: { kind: "statement", text: "", chips: {} }, comparison: { kind: "", words: "", incident: [], ordinary: [] }, grid: [], checks: [], people: [], not_in_pattern: [], look_further: [] }

describe("A claim's result", () => {
  it("names the verdict, the records cited and what was searched", () => {
    const c = { ...base, level: { key: "claim_contradicts", name: "Contradicts", verdict: "contradicts", sentence: "Contradicts the records. 4 positions", reasons: ["4 positions, 0 inside"], rule: "claim" },
      gaps: [], claim: { id: "c", sentence: "I was home all evening.", confirmed_by: "Test Person", edited: ["when"] },
      cited: [{ ref: "phone_record:1", at: "2025-01-03T19:00:00+00:00", person: "Ann Arden", inside: false }],
      searched: { records_read: { position: 4 }, window: { label: "Fri 03 Jan 18:00 to 23:59 (UTC)", start: "", end: "" } } } as unknown as Corroboration
    render(<ClaimResult c={c} />)
    expect(screen.getByRole("heading", { name: "Contradicts" })).toBeTruthy()
    expect(screen.getByText(/phone_record:1 · Ann Arden/)).toBeTruthy()
    expect(screen.getByText(/4 positions read/)).toBeTruthy()
    expect(screen.getByText(/Confirmed by Test Person; changed from Loupe's reading: when/)).toBeTruthy()
  })
})
