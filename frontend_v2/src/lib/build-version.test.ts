import { describe, expect, it } from "vitest"

import { isStaleBuild } from "./build-version"

describe("isStaleBuild", () => {
  it("is stale only when the served build differs from the loaded one", () => {
    expect(isStaleBuild({ build: "b2" }, "b1")).toBe(true)
    expect(isStaleBuild({ build: "b1" }, "b1")).toBe(false)
  })

  it("never shows the banner without both ids", () => {
    expect(isStaleBuild({}, "b1")).toBe(false)
    expect(isStaleBuild({ build: "b1" }, "")).toBe(false)
  })
})
