import { describe, expect, it } from "vitest"
import { evidenceWords, towerMccWords } from "./together-words"

describe("Together evidence words", () => {
  it("names each kind of evidence in plain words, with the cautions", () => {
    const w = evidenceWords({ "basis:coordinates": 3, "basis:bluetooth": 2, "flag:name_match": 1, "flag:nearby_not_connected": 1,
      "basis:shared_cell": 1, "flag:mcc_inferred": 1 })
    expect(w).toHaveLength(3)
    expect(w[0]).toBe("3 from recorded positions.")
    expect(w[1]).toContain("1 from the same cell tower seen by both phones")
    expect(w[1]).toContain("1 of them uses a country code taken from the phone's SIM card")
    expect(evidenceWords({ "basis:shared_cell": 3, "flag:mcc_inferred": 2 })[0]).toContain("2 of them use a country code")
    expect(w[2]).toContain("2 from one phone's Bluetooth seeing the other phone (about 30 m)")
    expect(w[2]).toContain("1 matched by device name only")
    expect(w[2]).toContain("1 nearby, not connected")
  })
  it("says how many Bluetooth sightings were not compared because a name is a factory default", () => {
    expect(evidenceWords({ "not_compared:default_device_name": 3 })).toEqual([
      "3 Bluetooth sightings not compared: the other phone's Bluetooth name is its factory default (its model name), which every phone of that model shares."])
  })
  it("says nothing for a run with no pairs", () => {
    expect(evidenceWords({})).toEqual([])
    expect(evidenceWords(undefined)).toEqual([])
  })
  it("counts the towers with a SIM country code", () => {
    expect(towerMccWords([{ mcc_inferred: true }, { mcc_inferred: false }], "Country code taken from the SIM.")).toBe(
      "1 of these towers: Country code taken from the SIM.")
    expect(towerMccWords([{ mcc_inferred: false }], "x")).toBeNull()
  })
})
