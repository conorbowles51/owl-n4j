import { describe, expect, it } from "vitest"
import { typeLabel, typeLabelPlural } from "./type-label"

describe("readable graph type names (lx-graphclarity C)", () => {
  it("names the run-together types the Graph shows today", () => {
    expect(typeLabel("financialtransaction")).toBe("Financial transaction")
    expect(typeLabel("phoneidentity")).toBe("Phone identity")
    expect(typeLabel("financialstatementperiod")).toBe("Statement period")
    expect(typeLabel("physicalevidence")).toBe("Physical evidence")
    expect(typeLabel("FinancialTransaction")).toBe("Financial transaction")
    expect(typeLabel("transaction")).toBe("Transaction")
    expect(typeLabel("person")).toBe("Person")
  })

  it("gives unknown types spaced words, never run-together", () => {
    expect(typeLabel("bankwallet")).toBe("Bank wallet")
    expect(typeLabel("CryptoWallet")).toBe("Crypto wallet")
    expect(typeLabel("money_transfer")).toBe("Money transfer")
    expect(typeLabel("zorblat")).toBe("Zorblat")
    expect(typeLabel("")).toBe("Other")
  })

  it("makes plurals for sentences", () => {
    expect(typeLabelPlural("phoneidentity")).toBe("phone identities")
    expect(typeLabelPlural("physicalevidence")).toBe("physical evidence")
    expect(typeLabelPlural("person")).toBe("people")
  })
})
