import { describe, expect, it } from "vitest"
import { verifyTraceAssets, type TraceAssetResults } from "./trace-assets"
const use = {
  transaction_id: "withdrawal",
  asset_label: "Equipment",
  basis: "Synthetic hypothesis",
}
const rows = [
  {
    key: "withdrawal",
    direction: "debit",
    amount_minor: "9007199254740993",
    currency: "GBP",
  },
]
const money = (minor_units: string) => ({ minor_units, currency: "GBP" })
const draw = {
  transaction_id: "withdrawal",
  amount: money(rows[0].amount_minor),
  by_claim: { claim: money("9007199254740990") },
  unidentified: money("1"),
  unfunded: money("0"),
}
const item: TraceAssetResults[number] = {
  ...use,
  amount_minor: rows[0].amount_minor,
  currency: "GBP",
  allocated_by_claim: { claim: "9007199254740990" },
  outside_claims_minor: "3",
  unidentified_minor: "1",
  unfunded_minor: "0",
  changes_cash_results: false,
  limitation: "Explicit hypothesis",
}
describe("asset withdrawal verification", () => {
  it("retains exact allocation above JavaScript's safe integer range", () =>
    expect(() => verifyTraceAssets([item], [use], rows, [draw])).not.toThrow())
  it("rejects changed attribution, source, residues and missing interpretations", () => {
    for (const changed of [
      { allocated_by_claim: { claim: "9007199254740989" } },
      { transaction_id: "other" },
      { basis: "different" },
      { outside_claims_minor: "4" },
      { unidentified_minor: "2" },
    ])
      expect(() =>
        verifyTraceAssets([{ ...item, ...changed }], [use], rows, [draw])
      ).toThrow()
    expect(() => verifyTraceAssets([], [use], rows, [draw])).toThrow()
    expect(() =>
      verifyTraceAssets([item, item], [use, use], rows, [draw])
    ).toThrow()
    expect(() =>
      verifyTraceAssets(
        [item],
        [use],
        [{ ...rows[0], direction: "credit" }],
        [draw]
      )
    ).toThrow()
    expect(() =>
      verifyTraceAssets([item], [use], rows, [
        { ...draw, unidentified: { minor_units: "1", currency: "USD" } },
      ])
    ).toThrow()
  })
  it("permits an empty optional section", () =>
    expect(() => verifyTraceAssets([], undefined, rows, [draw])).not.toThrow())
})
