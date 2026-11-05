import { describe, expect, it } from "vitest"
import fields from "./ux-event-fields.json"
import { phoneScreen } from "./phone-screen"

const C = "/cases/c1"
const PHONE_ADDRESSES = [
  `${C}/phones`, `${C}/phones/x`, `${C}/phones/x/records/conversations`, `${C}/phones/x/records/media`,
  `${C}/phones/x/records/media/spread`, `${C}/phones/x/records/Contact`, `${C}/records/r1`, `${C}/conversations`,
  `${C}/phone-review`, `${C}/phone-patterns`, `${C}/phone-money`, `${C}/phone-analyses/deletions`, `${C}/search`,
  `${C}/keyword-lists`,
]

describe("phoneScreen", () => {
  it("names every phone address with a screen the server accepts", () => {
    const allowed = fields.field_types.screen.enum
    for (const a of PHONE_ADDRESSES) expect(allowed, a).toContain(phoneScreen(a))
  })
  it("reads the list for a record type and the two named record screens apart", () => {
    expect(phoneScreen(`${C}/phones/x/records/Contact`)).toBe("phone-records")
    expect(phoneScreen(`${C}/phones/x/records/media`)).toBe("media")
    expect(phoneScreen(`${C}/phones/x/records/conversations`)).toBe("conversations")
    expect(phoneScreen(`${C}/phones/x/`)).toBe("phone-summary")
  })
  it("is null off the phone screens", () => {
    for (const a of ["/", "/cases", C, `${C}/workspace`, `${C}/financial`, `${C}/graph`, `${C}/phones-prototype/summary`]) expect(phoneScreen(a), a).toBeNull()
  })
})
