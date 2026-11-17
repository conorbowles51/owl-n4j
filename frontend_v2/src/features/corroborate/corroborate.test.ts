import { beforeEach, describe, expect, it } from "vitest"
import { addPart, clearSelection, getSelection, removePart, selectionCount, selectionMembers } from "./selection-store"
import { hitTest, linksBetween, pointInBox, pointInPolygon } from "./lasso"

beforeEach(() => localStorage.clear())

const pay = (n: number) => ({ type: "financial_transaction", id: `p${n}` })

describe("the case-wide selection", () => {
  it("holds a mix of record types, one chip per part, and survives a reload", () => {
    addPart("c1", { screen: "the map", label: "Warehouse lasso", members: [{ type: "phone_record", id: "r1" }, { type: "place", id: "1,2,50" }], skipped: [] })
    addPart("c1", { screen: "the graph", label: "Kell, Okafor", members: [{ type: "graph_entity", id: "k" }, { type: "graph_entity", id: "o" }], skipped: [] })
    addPart("c1", { screen: "the ledger", label: "Pocketwire", members: [1, 2, 3, 4, 5].map(pay), skipped: [{ type: "interview", count: 1 }] })
    const reloaded = getSelection("c1") // read back from storage, as a new page would
    expect(reloaded.map((p) => p.screen)).toEqual(["the map", "the graph", "the ledger"])
    expect(new Set(selectionMembers(reloaded).map((m) => m.type))).toEqual(new Set(["phone_record", "place", "graph_entity", "financial_transaction"]))
    expect(selectionCount(reloaded)).toBe(9)
    expect(reloaded[2].skipped).toEqual([{ type: "interview", count: 1 }]) // named, not dropped
  })

  it("counts the whole set, never a page, and counts an item in two parts once", () => {
    const all = Array.from({ length: 2500 }, (_, i) => pay(i))
    addPart("c1", { screen: "the ledger", label: "All filtered", members: all, skipped: [] })
    addPart("c1", { screen: "the timeline", label: "Brush", members: [pay(0), pay(1), { type: "evidence", id: "e1" }], skipped: [] })
    expect(selectionCount(getSelection("c1"))).toBe(2501)
  })

  it("removes one part, and clears until cleared", () => {
    const a = addPart("c1", { screen: "a", label: "A", members: [pay(1)], skipped: [] })
    addPart("c1", { screen: "b", label: "B", members: [pay(2)], skipped: [] })
    removePart("c1", a.id)
    expect(getSelection("c1").map((p) => p.label)).toEqual(["B"])
    clearSelection("c1")
    expect(getSelection("c1")).toEqual([])
  })

  it("keeps cases apart and says how many were new", () => {
    expect(addPart("c1", { screen: "a", label: "A", members: [pay(1), pay(2)], skipped: [] }).added).toBe(2)
    expect(addPart("c1", { screen: "a", label: "B", members: [pay(2), pay(3)], skipped: [] }).added).toBe(1)
    expect(getSelection("c2")).toEqual([])
  })
})

describe("lasso hit-testing", () => {
  const square = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }]
  it("takes points inside a polygon and not outside", () => {
    expect(pointInPolygon({ x: 5, y: 5 }, square)).toBe(true)
    expect(pointInPolygon({ x: 11, y: 5 }, square)).toBe(false)
    expect(pointInPolygon({ x: 5, y: 5 }, square.slice(0, 2))).toBe(false)
  })
  it("handles a concave lasso", () => {
    const u = [{ x: 0, y: 0 }, { x: 9, y: 0 }, { x: 9, y: 9 }, { x: 6, y: 9 }, { x: 6, y: 3 }, { x: 3, y: 3 }, { x: 3, y: 9 }, { x: 0, y: 9 }]
    expect(pointInPolygon({ x: 4, y: 6 }, u)).toBe(false)
    expect(pointInPolygon({ x: 1, y: 6 }, u)).toBe(true)
  })
  it("tests every point on its own position, including points that share a cluster, and lists the unplaced", () => {
    const pts = [{ id: "a", p: { x: 5, y: 5 } }, { id: "b", p: { x: 5.001, y: 5.001 } }, { id: "c", p: { x: 50, y: 5 } }, { id: "d", p: null }]
    const out = hitTest(pts, (i) => i.p, square)
    expect(out.hits.map((i) => i.id)).toEqual(["a", "b"])
    expect(out.unplaced.map((i) => i.id)).toEqual(["d"])
  })
  it("takes the links whose two ends are both inside", () => {
    const links: [string, string][] = [["k", "o"], ["k", "x"]]
    expect(linksBetween(links, (l) => l, new Set(["k", "o"]))).toEqual([["k", "o"]])
  })
  it("tests a box in either drag direction", () => {
    expect(pointInBox({ x: 5, y: 5 }, { x: 10, y: 10 }, { x: 0, y: 0 })).toBe(true)
  })
})
