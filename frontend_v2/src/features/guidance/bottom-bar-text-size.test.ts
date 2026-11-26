import { describe, expect, it } from "vitest"
import bar from "./CaseGuidanceBar.tsx?raw"
import guide from "./GuideMenu.tsx?raw"
import strip from "./history/HistoryStrip.tsx?raw"

// The case bottom bar (History, Guide, the step strip) is on every case page. Text a person reads there is 12 px or
// larger; it measured 11 px live on every page at 1440 and 390 (lx-phonesetup, 26 Nov). A decorative mark hidden from
// screen readers may stay smaller.
describe("the case bottom bar's text size", () => {
  it.each([["CaseGuidanceBar", bar], ["GuideMenu", guide], ["HistoryStrip", strip]])("%s has no readable text under 12 px", (_name, src) => {
    const small = src.split("\n").filter((l) => /text-\[(?:[0-9]|1[01])px\]/.test(l) && !/aria-hidden="true"/.test(l))
    expect(small).toEqual([])
  })
})
