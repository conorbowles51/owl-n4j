import { describe, expect, it } from "vitest"
import { commonWords } from "./common-words"

/** 05 16a.8 on the screen: both sides' counts, the contact's own phone, and saved with no contact. Invented data only. */
const side = (total: number, other = 0, saved = 0) => ({ total, on_own_phones: total - other, seen_on_other_phone: other, first: total ? "2023-01-02T09:00:00Z" : null, last: total ? "2023-01-02T09:00:00Z" : null, saved })
const r = (kind: string, a: ReturnType<typeof side>, b: ReturnType<typeof side>) => ({
  id: "r", kind, strength: "x", label: "Lead for enquiry", decision: null, decisions: [], period_start: null, period_end: null,
  directions: { supports: [], undercuts: [] }, measures: { owner_a: "C1", owner_b: "C2", contact_display: "Synthetic Person", a, b } }) as never

describe("Common contacts words", () => {
  it("states each side, singular and plural, and the contact's own phone", () => {
    const w = commonWords(r("common_contact", side(1), side(3, 1)))
    expect(w.title).toBe("Synthetic Person: linked to C1 and C2")
    expect(w.line).toContain("C1: 1 call, message or email from")
    expect(w.line).toContain("C2: 3 calls, messages or emails (1 of them on the contact's own phone)")
  })
  it("says saved with no contact seen", () => {
    expect(commonWords(r("saved_no_contact", side(0, 0, 1), side(2))).line).toContain("C1: saved as a contact, no call, message or email seen")
  })
})
