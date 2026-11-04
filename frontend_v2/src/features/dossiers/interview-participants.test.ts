import { describe, expect, it } from "vitest"
import { buildParticipants, splitParticipants } from "./interview-participants"

describe("interviewed by (FEAT-010)", () => {
  it("keeps the interviewer apart from the participants", () => {
    const stored = ["Jane Roe", { name: "Det. Smith, county police", role: "interviewed_by" }]
    expect(splitParticipants(stored)).toEqual({ names: ["Jane Roe"], interviewedBy: "Det. Smith, county police" })
  })

  it("saves the interviewer as its own record and keeps existing participant records whole", () => {
    const existing = [{ name: "Jane Roe", phone: "555-0100" }, "Old Name"]
    expect(buildParticipants("Jane Roe, New Person", "Deposition, defence counsel", existing)).toEqual([
      { name: "Jane Roe", phone: "555-0100" },
      "New Person",
      { name: "Deposition, defence counsel", role: "interviewed_by" },
    ])
    expect(buildParticipants("Jane Roe", "", existing)).toEqual([{ name: "Jane Roe", phone: "555-0100" }])
  })
})
