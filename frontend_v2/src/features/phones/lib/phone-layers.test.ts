import { describe, expect, it } from "vitest"
import { groupByOwner, layersOn, onlyLayer, toChosen, toggleLayer } from "./phone-layers"

const all = ["a", "b", "c"]

describe("phone layers", () => {
  it("an empty choice is every phone", () => expect(layersOn(all, [])).toEqual(all))
  it("switching one off keeps the others, in case order", () => expect(toggleLayer(all, [], "b")).toEqual(["a", "c"]))
  it("switching it back on returns to the empty choice", () => expect(toggleLayer(all, ["a", "c"], "b")).toEqual([]))
  it("the last phone on cannot be switched off", () => expect(toggleLayer(all, ["a"], "a")).toEqual(["a"]))
  it("only this", () => expect(onlyLayer(all, "c")).toEqual(["c"]))
  it("a stale id in the address is ignored, and an all-stale list is every phone", () => {
    expect(layersOn(all, ["a", "zzz"])).toEqual(["a"])
    expect(layersOn(all, ["zzz"])).toEqual(all)
    expect(toChosen(all, ["c", "a", "b"])).toEqual([])
  })

  it("groups by owner with owners in name order, no owner last, and finds by label or owner", () => {
    const ps = [{ label: "C1", owner: "Lena Marsh" }, { label: "C2", owner: null }, { label: "C3", owner: "Travis Kell" }, { label: "C4", owner: "Lena Marsh" }]
    expect(groupByOwner(ps).map((g) => [g.owner, g.phones.map((p) => p.label)])).toEqual([["Lena Marsh", ["C1", "C4"]], ["Travis Kell", ["C3"]], [null, ["C2"]]])
    expect(groupByOwner(ps, "kell").map((g) => g.phones.map((p) => p.label))).toEqual([["C3"]])
    expect(groupByOwner(ps, "c2")[0].owner).toBeNull()
  })
})
