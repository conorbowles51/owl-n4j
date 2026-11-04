import { describe, expect, it } from "vitest"
import { identifierText } from "./labels"

describe("Bluetooth identities in plain words", () => {
  it("says what the value is", () => {
    expect(identifierText({ kind: "other", subkind: "bluetooth_address", display: "0A:1B:2C:3D:4E:5F" } as never)).toBe(
      "Bluetooth address 0A:1B:2C:3D:4E:5F")
    expect(identifierText({ kind: "other", subkind: "bluetooth_name", display: "Synthetic Handset" } as never)).toBe(
      "Bluetooth name Synthetic Handset")
    expect(identifierText({ kind: "phone", subkind: null, display: "+1 202-555-0100" } as never)).toBe("+1 202-555-0100")
  })
})
