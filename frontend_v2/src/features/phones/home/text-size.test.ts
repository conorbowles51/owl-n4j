import { describe, expect, it } from "vitest"
import page from "./PhonesHome.tsx?raw"
import panel from "./HomeRecordPanel.tsx?raw"
import strip from "./ActivityStrip.tsx?raw"

// Text a person reads on the Phones page is 12 px or larger (the strip's month labels measured 11 px live at 390).
describe("the Phones page's text size", () => {
  it.each([["PhonesHome", page], ["HomeRecordPanel", panel], ["ActivityStrip", strip]])("%s has no readable text under 12 px", (_name, src) => {
    expect(src.split("\n").filter((l) => /text-\[(?:[0-9]|1[01])px\]/.test(l) && !/aria-hidden="true"/.test(l))).toEqual([])
  })
})
