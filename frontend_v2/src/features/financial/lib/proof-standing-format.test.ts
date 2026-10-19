import { describe, expect, it } from "vitest"
import { proofStanding } from "@/test/proof-standing-fixture"
import { readProofStanding } from "./proof-standing-format"

describe("validating the evidence classification census", () => {
  it("preserves the entire backend response including empty classes", () => {
    const data = proofStanding()
    expect(readProofStanding(data, "case-1")).toBe(data)
    expect(data.classes[0].documents).toBe(0)
  })
  it.each([
    { case_id: "other-case" },
    { classes: [] },
    { documents: 6 },
    { transactions: -1 },
    { documents_requiring_adjudication: 0 },
    { transactions_requiring_adjudication: 3 },
    { counted_classes: ["p0"] },
    { counted_classes: ["p0", "p1", "p2", "p2"] },
  ])("refuses an inconsistent census: %j", (change) => {
    expect(() =>
      readProofStanding({ ...proofStanding(), ...change }, "case-1")
    ).toThrow()
  })
  it.each([undefined, null, {}, []])(
    "refuses incomplete responses: %j",
    (value) => {
      expect(() => readProofStanding(value, "case-1")).toThrow()
    }
  )
  it.each([
    "admits_automatically",
    "requires_adjudication",
    "may_produce_ledger_rows",
    "counts_toward_totals",
  ])("does not default a missing %s rule", (field) => {
    const data = proofStanding()
    const row = data.classes[0] as unknown as Record<string, unknown>
    delete row[field]
    expect(() => readProofStanding(data, "case-1")).toThrow(/rules/)
  })
  it("does not omit future classes or invent their permissions", () => {
    const data = proofStanding()
    data.classes.push({ ...data.classes[3], proof_class: "p5" })
    data.documents += 2
    data.transactions += 4
    data.documents_requiring_adjudication += 2
    data.transactions_requiring_adjudication += 4
    expect(readProofStanding(data, "case-1").classes.at(-1)?.proof_class).toBe(
      "p5"
    )
  })
  it("reads changed permission rules from the response instead of deriving them from a class name", () => {
    const data = proofStanding()
    data.classes[1].requires_adjudication = true
    data.classes[1].admits_automatically = false
    data.documents_requiring_adjudication += 1
    data.transactions_requiring_adjudication += 2
    expect(
      readProofStanding(data, "case-1").classes[1].requires_adjudication
    ).toBe(true)
  })
  it("refuses duplicated classes and unsafe integer counts", () => {
    const data = proofStanding()
    data.classes.push(data.classes[0])
    expect(() => readProofStanding(data, "case-1")).toThrow()
    const unsafe = proofStanding()
    unsafe.classes[0].documents = Number.MAX_SAFE_INTEGER + 1
    expect(() => readProofStanding(unsafe, "case-1")).toThrow()
  })
})
