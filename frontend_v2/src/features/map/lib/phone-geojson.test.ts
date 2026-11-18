import { describe, expect, it } from "vitest"
import type { PhoneMapItem } from "@/features/phones/api"
import { phoneGeoJSON } from "./phone-geojson"

const point = (record_uid: string): PhoneMapItem => ({
  type: "point", point_uid: `p-${record_uid}`, record_uid, extraction_id: "x1", phone_label: "Phone 1",
  lat: 39.29, lon: -76.61, accuracy_m: 8,
} as unknown as PhoneMapItem)

describe("phoneGeoJSON", () => {
  it("marks the points of the lead shown with Show these records, and never a cluster", () => {
    const items = [point("in-lead"), point("other"), { type: "cluster", count: 4, lat: 39.3, lon: -76.6 } as unknown as PhoneMapItem]
    const fc = phoneGeoJSON(items, (uid) => uid === "in-lead")
    expect(fc.features.map((f) => f.properties?.shown)).toEqual([true, false, false])
  })

  it("marks nothing when no lead is shown", () => {
    expect(phoneGeoJSON([point("in-lead")]).features[0].properties?.shown).toBe(false)
  })
})
