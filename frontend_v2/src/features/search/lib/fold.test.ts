import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import tables from "./fold-tables.json"
import { fold, foldWithMap, matchRanges } from "./fold"

/** A8 and 03 section 11.3: the browser's fold against the fixture the backend reads too. */
const root = resolve(__dirname, "../../../../../backend")
const cases = JSON.parse(readFileSync(resolve(root, "tests/fixtures/fold_cases.json"), "utf-8")).cases as { name: string; input: string; fold?: string; exact?: string }[]

describe("fold (shared fixture)", () => {
  it.each(cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    if (c.fold !== undefined) expect(fold(c.input)).toBe(c.fold)
    if (c.exact !== undefined) expect(fold(c.input, true)).toBe(c.exact)
  })

  it("uses the backend's tables unchanged", () => {
    const styled = JSON.parse(readFileSync(resolve(root, "services/phone/data/styled_letters.json"), "utf-8")).map
    const confusable = JSON.parse(readFileSync(resolve(root, "services/phone/data/confusables_latin.json"), "utf-8")).map
    expect(tables.styled).toEqual(styled)
    expect(tables.confusable).toEqual(confusable)
  })
})

describe("foldWithMap and matchRanges (S-5, S-8)", () => {
  it.each(cases.map((c) => [c.name, c] as const))("equals fold on %s", (_name, c) => {
    if (c.fold !== undefined) expect(foldWithMap(c.input).folded).toBe(c.fold)
    if (c.exact !== undefined) expect(foldWithMap(c.input, true).folded).toBe(c.exact)
  })
  it("finds matches on the original characters after length-changing folds", () => {
    const text = "Paid  \uFB01ne to Jos\u00e9 \u{1D4D9}\u{1D4F8}\u{1D4FC}\u{1D4EE}, Stra\u00dfe 5"
    const at = (q: string) => matchRanges(text, q).map(([a, b]) => text.slice(a, b))
    expect(at("fine")).toEqual(["\uFB01ne"])
    expect(at("jose")).toEqual(["Jos\u00e9", "\u{1D4D9}\u{1D4F8}\u{1D4FC}\u{1D4EE}"])
    expect(at("strasse")).toEqual(["Stra\u00dfe"])
    expect(matchRanges(text, "jose", true).map(([a, b]) => text.slice(a, b))).toEqual([])
  })
})
