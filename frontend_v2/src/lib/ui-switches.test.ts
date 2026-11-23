import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { applySwitchesFromSearch, isSwitchOn, setSwitch } from "@/lib/ui-switches"

beforeEach(() => localStorage.clear())
afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })

describe("switch defaults (Neil 23 Nov: 'yes turn on corroborate')", () => {
  it("a new browser with no setting has Corroborate on and the phone prototype off", () => {
    expect(isSwitchOn("corroborate-v2")).toBe(true)
    expect(isSwitchOn("phone-prototype")).toBe(false)
  })
  it("?corroborate-v2=off turns Corroborate off for this browser, and =on back on", () => {
    applySwitchesFromSearch("?corroborate-v2=off")
    expect(isSwitchOn("corroborate-v2")).toBe(false)
    expect(localStorage.getItem("loupe.switch.corroborate-v2")).toBe("off")
    applySwitchesFromSearch("?corroborate-v2=on")
    expect(isSwitchOn("corroborate-v2")).toBe(true)
  })
  it("an older browser that stored 'on' keeps it on", () => {
    localStorage.setItem("loupe.switch.corroborate-v2", "on")
    expect(isSwitchOn("corroborate-v2")).toBe(true)
  })
  it("the phone prototype still needs ?phone-prototype=on", () => {
    applySwitchesFromSearch("?phone-prototype=on")
    expect(isSwitchOn("phone-prototype")).toBe(true)
    setSwitch("phone-prototype", false)
    expect(isSwitchOn("phone-prototype")).toBe(false)
  })
  it("when storage fails, each switch keeps its default", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked") })
    expect(isSwitchOn("corroborate-v2")).toBe(true)
    expect(isSwitchOn("phone-prototype")).toBe(false)
  })
})
