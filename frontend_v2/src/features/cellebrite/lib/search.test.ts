import { describe, expect, it } from "vitest"
import type { PhoneReport } from "../types"
import {
  extractParticipantKeys,
  matchCellebriteItem,
  parseCellebriteQuery,
  splitForHighlight,
} from "./search"

const reports: PhoneReport[] = [
  {
    report_key: "phone-a",
    display_index: 0,
    device_model: "Pixel",
    phone_owner_name: "Alice",
  },
]

describe("parseCellebriteQuery", () => {
  it("parses scoped operators and negative terms", () => {
    const parsed = parseCellebriteQuery("app:WhatsApp from:Bob -spam after:2024-01-01")
    expect(parsed.operators.app).toBe("whatsapp")
    expect(parsed.operators.from).toBe("bob")
    expect(parsed.excludes).toEqual(["spam"])
    expect(parsed.operators.after).toBeTypeOf("number")
  })

  it("keeps URLs and other unknown colon tokens as free text", () => {
    const parsed = parseCellebriteQuery("http://example.test/a:b")
    expect(parsed.terms).toEqual(["http://example.test/a:b"])
  })

  it("parses near coordinates in metres", () => {
    const parsed = parseCellebriteQuery("near:51.5,-0.1,500m")
    expect(parsed.operators.near).toEqual({
      lat: 51.5,
      lng: -0.1,
      radiusMeters: 500,
    })
  })
})

describe("matchCellebriteItem", () => {
  it("matches phone/app/place scoped searches", () => {
    const parsed = parseCellebriteQuery("phone:p1 app:signal place:london")
    const result = matchCellebriteItem(
      {
        report_key: "phone-a",
        source_app: "Signal",
        place_name: "London Bridge",
      },
      parsed,
      "event",
      reports
    )
    expect(result.matches).toBe(true)
  })

  it("fails near searches when rows have no coordinates", () => {
    const parsed = parseCellebriteQuery("near:51.5,-0.1,5km")
    expect(matchCellebriteItem({}, parsed, "event", reports).matches).toBe(false)
  })
})

describe("highlight and participants helpers", () => {
  it("splits highlighted text into marked segments", () => {
    expect(splitForHighlight("WhatsApp message", ["whatsapp"])).toEqual([
      { text: "WhatsApp", match: true },
      { text: " message", match: false },
    ])
  })

  it("extracts direction-agnostic participant keys from rollup rows", () => {
    expect(
      extractParticipantKeys({
        participant_keys: ["person-1", "person-2"],
        key: "fallback",
      })
    ).toEqual(["person-1", "person-2"])
  })
})
