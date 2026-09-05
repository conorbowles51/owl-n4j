/**
 * Reading a ledger row for display.
 *
 * The money tests are the point of this file. `amount_minor` is an integer and
 * the figure a person reads is not, so something has to put the decimal point
 * in, and putting it in the wrong place by a factor of ten is the single
 * cheapest way to make this system lie. The cases below are the ones that
 * would let it: a currency with no minor unit, a currency with three of them,
 * an amount smaller than one major unit, and an amount large enough that
 * dividing would cost it its last cent.
 *
 * The vocabulary tests cover the other failure, which is quieter. A member
 * this build has never heard of has to arrive on the screen saying so. An
 * empty badge reads as an answer.
 */

import { describe, expect, it } from "vitest"

import {
  currencyMinorUnits,
  formatLedgerAmount,
  readDateSource,
  readDirection,
  readExtractionLayer,
  readLedgerStatus,
  readProofClass,
  readQuarantineReason,
} from "./ledger-format"

describe("currencyMinorUnits", () => {
  it("knows the ordinary case", () => {
    expect(currencyMinorUnits("USD")).toBe(2)
    expect(currencyMinorUnits("EUR")).toBe(2)
    expect(currencyMinorUnits("GBP")).toBe(2)
  })

  it("knows the currencies that are not two", () => {
    // The whole reason this function exists. A ledger that divided by a
    // hundred would report every yen figure as one hundredth of itself and
    // every dinar figure as ten times itself.
    expect(currencyMinorUnits("JPY")).toBe(0)
    expect(currencyMinorUnits("BHD")).toBe(3)
    expect(currencyMinorUnits("KWD")).toBe(3)
  })

  it("is case and whitespace insensitive, because a stored code may not be tidy", () => {
    expect(currencyMinorUnits(" usd ")).toBe(2)
  })

  it("refuses a code it cannot scale rather than assuming two", () => {
    expect(currencyMinorUnits("US")).toBeNull()
    expect(currencyMinorUnits("")).toBeNull()
    expect(currencyMinorUnits("DOLLARS")).toBeNull()
  })
})

describe("formatLedgerAmount", () => {
  it("puts the point where the currency says it goes", () => {
    expect(formatLedgerAmount(123456, "USD")).toEqual({
      text: "1,234.56",
      currency: "USD",
      scaled: true,
    })
  })

  it("leaves a currency with no minor unit whole", () => {
    // 123456 yen is 123,456 yen. Not 1,234.56.
    expect(formatLedgerAmount(123456, "JPY")).toEqual({
      text: "123,456",
      currency: "JPY",
      scaled: true,
    })
  })

  it("gives a three-decimal currency its three decimals", () => {
    expect(formatLedgerAmount(123456, "BHD")).toEqual({
      text: "123.456",
      currency: "BHD",
      scaled: true,
    })
  })

  it("pads an amount smaller than one major unit", () => {
    // Five cents, not five dollars, and not fifty.
    expect(formatLedgerAmount(5, "USD").text).toBe("0.05")
    expect(formatLedgerAmount(50, "USD").text).toBe("0.50")
    expect(formatLedgerAmount(0, "USD").text).toBe("0.00")
    expect(formatLedgerAmount(5, "BHD").text).toBe("0.005")
  })

  it("keeps the last cent of an amount too large to divide safely", () => {
    // 90,071,992,547,409.91 in cents. Dividing this by a hundred in floating
    // point does not land on it: the gap between representable numbers up here
    // is wider than a cent, so the result is rounded to something that is not
    // what the ledger stored. Cutting the digit string cannot round anything.
    expect(formatLedgerAmount(9007199254740991, "USD").text).toBe(
      "90,071,992,547,409.91"
    )
  })

  it("groups thousands the same way on every machine", () => {
    // Fixed rather than taken from the browser's locale, so two people
    // reading the same case see the same figure.
    expect(formatLedgerAmount(100000000, "USD").text).toBe("1,000,000.00")
    expect(formatLedgerAmount(100, "JPY").text).toBe("100")
    expect(formatLedgerAmount(1000, "JPY").text).toBe("1,000")
  })

  it("keeps a sign when one is there", () => {
    // `amount_minor` is a magnitude, but `running_balance_minor` can go below
    // zero and is formatted by this same function.
    expect(formatLedgerAmount(-123456, "USD").text).toBe("-1,234.56")
    expect(formatLedgerAmount(-5, "USD").text).toBe("-0.05")
    expect(formatLedgerAmount(-1, "JPY").text).toBe("-1")
  })

  it("says so rather than guessing when the currency cannot be scaled", () => {
    // The digits are shown as they were stored and `scaled` is false, so a
    // caller that renders this beside real figures has been told it is not
    // one. Silently assuming two decimals here would print a figure a hundred
    // times too small and nothing on the screen would say why.
    const result = formatLedgerAmount(123456, "DOLLARS")
    expect(result.scaled).toBe(false)
    expect(result.text).toBe("123,456")
  })

  it("says so rather than guessing when the stored amount is not a whole minor unit", () => {
    // Minor units are counted, not measured. A fraction here means the row was
    // written by something that did not respect that, and scaling it would
    // hide the fault behind a well-formed figure.
    expect(formatLedgerAmount(1234.5, "USD")).toEqual({
      text: "1234.5",
      currency: "USD",
      scaled: false,
    })
    expect(formatLedgerAmount(Number.NaN, "USD").scaled).toBe(false)
    expect(formatLedgerAmount(1e21, "USD").scaled).toBe(false)
  })

  it("reports the code as stored, upper-cased", () => {
    expect(formatLedgerAmount(1, "usd").currency).toBe("USD")
  })
})

describe("reading a closed vocabulary", () => {
  it("names the members it knows", () => {
    expect(readLedgerStatus("admitted").value).toBe("admitted")
    expect(readLedgerStatus("admitted").label).toBe("Admitted")
    expect(readProofClass("p2").value).toBe("p2")
    expect(readDirection("debit").label).toBe("Debit")
    expect(readDateSource("value").label).toBe("Value date")
    expect(readQuarantineReason("balance_break").label).toBe("Balance break")
  })

  it("carries a description for every member, not just a label", () => {
    // What a status means to an investigation is the part worth reading. The
    // label alone is a word.
    for (const term of [
      readLedgerStatus("quarantined"),
      readProofClass("p4"),
      readDirection("credit"),
      readDateSource("posted"),
      readQuarantineReason("unexplained_delta"),
    ]) {
      expect(term.description.length).toBeGreaterThan(20)
    }
  })

  it("says it does not know a member rather than going blank", () => {
    // A newer backend can send a member this build has never heard of. An
    // empty badge in that column reads as an answer -- as though the row had
    // no status -- rather than as this screen being out of date.
    const status = readLedgerStatus("embargoed")
    expect(status.value).toBeNull()
    expect(status.raw).toBe("embargoed")
    expect(status.label).toContain("embargoed")
    expect(status.label).not.toBe("")
    expect(status.description).not.toBe("")
  })

  it("does not let one vocabulary answer for another", () => {
    // `admitted` is a member of LedgerStatus and of nothing else here. A
    // reader that accepted it would put a status where a proof class belongs.
    expect(readProofClass("admitted").value).toBeNull()
    expect(readDirection("p0").value).toBeNull()
    expect(readQuarantineReason("admitted").value).toBeNull()
    expect(readDateSource("admitted").value).toBeNull()
  })

  it("treats an empty string as unrecognised, not as absent", () => {
    // `quarantine_reason` is null when there is no reason. An empty string is
    // a different thing: a reason that was stored and cannot be read.
    expect(readQuarantineReason("").value).toBeNull()
    expect(readQuarantineReason("").label).not.toBe("")
  })
})

describe("readExtractionLayer", () => {
  it("names each layer", () => {
    expect(readExtractionLayer(0).label).toBe("Native")
    expect(readExtractionLayer(1).label).toBe("Template")
    expect(readExtractionLayer(2).label).toBe("Structural")
    expect(readExtractionLayer(3).label).toBe("Grounded model")
  })

  it("marks the fallback layer and only the fallback layer", () => {
    // Layer 3 is a marked fallback rather than a normal path, and a ledger
    // built mostly from it is one to be explained. A caller cannot draw
    // attention to that unless something tells it which layer is which.
    expect(readExtractionLayer(3).isFallback).toBe(true)
    expect(readExtractionLayer(0).isFallback).toBe(false)
    expect(readExtractionLayer(1).isFallback).toBe(false)
    expect(readExtractionLayer(2).isFallback).toBe(false)
  })

  it("says it does not know a layer outside the range", () => {
    const unknown = readExtractionLayer(4)
    expect(unknown.value).toBeNull()
    expect(unknown.label).toContain("4")
    expect(unknown.isFallback).toBe(false)
  })
})
