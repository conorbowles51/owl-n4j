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

it("checks partial allocations, conserved rounding and unchanged cash amount", () => {
  const partialUse = {
    ...use,
    asset_amount_minor: "3",
    allocation_basis: "proportional_share",
  }
  const partialRows = [{ ...rows[0], amount_minor: "10" }]
  const partialDraw = {
    ...draw,
    amount: money("10"),
    by_claim: { claim: money("5") },
    from_untainted: money("5"),
    from_opening: money("0"),
    unidentified: money("0"),
    unfunded: money("0"),
  }
  const partialItem = {
    ...item,
    amount_minor: "10",
    asset_amount_minor: "3",
    remaining_withdrawal_minor: "7",
    allocation_basis: "proportional_share" as const,
    allocated_by_claim: { claim: "2" },
    outside_claims_minor: "1",
    unidentified_minor: "0",
    unfunded_minor: "0",
  }
  expect(() =>
    verifyTraceAssets([partialItem], [partialUse], partialRows, [partialDraw])
  ).not.toThrow()
  for (const change of [
    { allocated_by_claim: { claim: "1" }, outside_claims_minor: "2" },
    { remaining_withdrawal_minor: "8" },
    { allocation_basis: "whole_withdrawal" as const },
    { asset_amount_minor: "4" },
  ])
    expect(() =>
      verifyTraceAssets(
        [{ ...partialItem, ...change }],
        [partialUse],
        partialRows,
        [partialDraw]
      )
    ).toThrow()
  expect(() =>
    verifyTraceAssets(
      [partialItem],
      [{ ...partialUse, asset_amount_minor: "11" }],
      partialRows,
      [partialDraw]
    )
  ).toThrow()
  expect(() =>
    verifyTraceAssets([partialItem], [partialUse], partialRows, [
      { ...partialDraw, from_untainted: undefined },
    ])
  ).toThrow()
})
it("uses Unicode code-point claim order for proportional rounding ties", () => {
  const keys = ["\u{10000}", "\uE000"]
  const d = {
    ...draw,
    amount: money("2"),
    by_claim: Object.fromEntries(keys.map((k) => [k, money("1")])),
    from_untainted: money("0"),
    from_opening: money("0"),
    unidentified: money("0"),
    unfunded: money("0"),
  }
  const a = {
    ...item,
    amount_minor: "2",
    asset_amount_minor: "1",
    remaining_withdrawal_minor: "1",
    allocation_basis: "proportional_share" as const,
    allocated_by_claim: { [keys[0]]: "0", [keys[1]]: "1" },
    outside_claims_minor: "0",
    unidentified_minor: "0",
    unfunded_minor: "0",
  }
  expect(() =>
    verifyTraceAssets(
      [a],
      [
        {
          ...use,
          asset_amount_minor: "1",
          allocation_basis: "proportional_share",
        },
      ],
      [{ ...rows[0], amount_minor: "2" }],
      [d]
    )
  ).not.toThrow()
})

it("allocates repeated withdrawals from remaining components without double counting a rounding unit", () => {
  const request = {
    ...use,
    asset_amount_minor: "1",
    allocation_basis: "proportional_share",
  }
  const smallRows = [{ ...rows[0], amount_minor: "2" }]
  const smallDraw = {
    ...draw,
    amount: money("2"),
    by_claim: { claim: money("1") },
    from_untainted: money("1"),
    from_opening: money("0"),
    unidentified: money("0"),
    unfunded: money("0"),
  }
  const first = {
    ...item,
    amount_minor: "2",
    asset_amount_minor: "1",
    remaining_withdrawal_minor: "1",
    allocation_basis: "proportional_share" as const,
    allocation_sequence: 1,
    allocated_by_claim: { claim: "1" },
    outside_claims_minor: "0",
    unidentified_minor: "0",
  }
  const second = {
    ...first,
    allocation_sequence: 2,
    remaining_withdrawal_minor: "0",
    allocated_by_claim: { claim: "0" },
    outside_claims_minor: "1",
  }
  expect(() =>
    verifyTraceAssets([first, second], [request, request], smallRows, [
      smallDraw,
    ])
  ).not.toThrow()
  for (const changed of [
    { allocated_by_claim: { claim: "1" }, outside_claims_minor: "0" },
    { allocation_sequence: 1 },
    { remaining_withdrawal_minor: "1" },
  ]) {
    expect(() =>
      verifyTraceAssets(
        [first, { ...second, ...changed }],
        [request, request],
        smallRows,
        [smallDraw]
      )
    ).toThrow()
  }
  expect(() =>
    verifyTraceAssets(
      [first, second, second],
      [request, request, request],
      smallRows,
      [smallDraw]
    )
  ).toThrow()
})
