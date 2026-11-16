import { describe, expect, it } from "vitest"
import { layersOn, onlyLayer, toChosen, toggleLayer } from "./phone-layers"

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
})
