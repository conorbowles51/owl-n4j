import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import tables from "./fold-tables.json"
import { fold } from "./fold"

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
