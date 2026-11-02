import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import {
  ZONE_TABLE,
  dayOf,
  dayRange,
  formatDayHeader,
  formatFull,
  formatRowTime,
  formatWall,
  validZone,
  zoneLabel,
} from "./evidence-time"

// 03 section 3.2, test A6 (T-time): the fixture the backend suite also reads.
const root = resolve(__dirname, "../../../backend")
const cases = JSON.parse(readFileSync(resolve(root, "tests/fixtures/time_cases.json"), "utf-8"))
const zones = JSON.parse(readFileSync(resolve(root, "services/phone/data/zone_names.json"), "utf-8"))

describe("evidence-time against the shared fixture", () => {
  for (const c of cases.instants) {
    it(`instant ${c.id}`, () => {
      expect(formatRowTime(c.instant, c.zone)).toBe(c.row)
      expect(formatRowTime(c.instant, c.zone, true)).toBe(c.row_seconds)
      expect(formatFull(c.instant, c.zone)).toBe(c.full)
      expect(dayOf(c.instant, c.zone)).toBe(c.day)
    })
  }
  for (const d of cases.days) {
    it(`day ${d.day} ${d.zone}`, () => {
      expect(formatDayHeader(d.day)).toBe(d.header)
      expect(zoneLabel(d.day, d.zone)).toBe(d.zone_label)
    })
  }
  for (const w of cases.walls) {
    it(`wall ${w.wall}`, () => {
      expect(formatWall(w.wall)).toBe(w.full)
    })
  }

  it("uses the same zone table as the backend", () => {
    expect(ZONE_TABLE).toEqual(zones.zones)
  })

  it("never prints Invalid Date and refuses an instant without an offset", () => {
    expect(formatFull(null, "UTC")).toBe("No time recorded")
    expect(() => formatFull("2023-03-14T19:07:12", "UTC")).toThrow()
  })

  it("converts a picked date to that day's instants in the zone", () => {
    expect(dayRange("2023-03-12", "America/New_York")).toEqual({
      from: "2023-03-12T05:00:00.000Z",
      to: "2023-03-13T03:59:59.999Z",
    })
    expect(validZone("America/New_York")).toBe(true)
    expect(validZone("Mars/Olympus")).toBe(false)
  })
})
