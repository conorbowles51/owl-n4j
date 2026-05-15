import { describe, expect, it } from "vitest"
import type { PhoneReport } from "../types"
import {
  getPhoneIdentity,
  getPhoneIdentityByKey,
  paletteSlotForKey,
  phoneShortLabel,
} from "./phone-identity"

const reports: PhoneReport[] = [
  {
    report_key: "cellebrite-one",
    display_index: 0,
    device_model: "iPhone 12",
    phone_owner_name: "Neil",
  },
  {
    report_key: "cellebrite-two",
    display_index: 4,
    device_name_override: "Burner A",
  },
]

describe("phone identity", () => {
  it("uses backend display index for stable labels and palette slots", () => {
    expect(phoneShortLabel(reports[1], reports)).toBe("P5")
    expect(getPhoneIdentity(reports[1], reports).palette.name).toBe("violet")
  })

  it("falls back to report order when display index is missing", () => {
    const withoutIndex: PhoneReport = { report_key: "cellebrite-three" }
    expect(phoneShortLabel(withoutIndex, [...reports, withoutIndex])).toBe("P3")
  })

  it("returns stable hash-based identity for unknown report keys", () => {
    expect(paletteSlotForKey("missing", reports)).toBe(paletteSlotForKey("missing", reports))
    expect(getPhoneIdentityByKey("missing", reports).short).toBe("P?")
  })
})
