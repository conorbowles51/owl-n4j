import { describe, expect, it } from "vitest"
import type { DayResponse } from "./api"
import { laneRowsOf } from "./lanes-lib"

const day = (flag_words?: Record<string, string>) => ({
  availability: [], totals: {}, lane_words: { passive: "Records" }, flag_words,
  lanes: { passive: [{ ref_kind: "activity_event", id: "e1", at: "2023-03-14T19:07:12+00:00", end: null, field: "TimeStamp", meaning: "event_instant",
                       strength: "none", actor: "owner", flags: ["affiliation_unknown", "not_worded"], source_app: "Gmail", phone: "Phone 1", record_uid: "r1", record_type: "Location" }] },
}) as unknown as DayResponse

describe("a lane item's flags (04 section 4.2)", () => {
  it("reads as the words the day view sends, never as the flag's code", () => {
    const passive = laneRowsOf("c1", day({ affiliation_unknown: "Not known whether this device recorded it." })).find((r) => r.id === "passive")!
    expect(passive.marks[0].detail).toContain("Not known whether this device recorded it.")
    expect(passive.marks[0].detail).not.toContain("affiliation_unknown")
    expect(passive.marks[0].detail).toContain("not_worded") // a flag with no words stays visible
  })
})
