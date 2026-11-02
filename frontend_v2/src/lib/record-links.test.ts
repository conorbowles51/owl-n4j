import { describe, expect, it } from "vitest"
import { parseRecordHref, recordPath } from "./record-links"

const UID = "3af41de3-c6aa-4b1e-9d0e-2f4f0df3ffe5"

describe("rec:// citations (03 section 11.5)", () => {
  it("reads a record id with or without a field path", () => {
    expect(parseRecordHref(`rec://${UID}`)).toEqual({ recordUid: UID, fieldPath: null })
    expect(parseRecordHref(`rec://${UID.toUpperCase()}#Body`)).toEqual({ recordUid: UID, fieldPath: "Body" })
    expect(parseRecordHref(`rec://${UID}#Parties%2F0`)).toEqual({ recordUid: UID, fieldPath: "Parties/0" })
  })
  it("refuses anything that is not one record id", () => {
    for (const h of ["doc://a.pdf/1", "rec://", "rec://not-a-uid", "https://x.test", undefined]) expect(parseRecordHref(h)).toBeNull()
  })
  it("opens the record route of the case", () => {
    expect(recordPath("case-1", UID)).toBe(`/cases/case-1/records/${UID}`)
    expect(recordPath("case-1", UID, "Body")).toBe(`/cases/case-1/records/${UID}#Body`)
  })
})
