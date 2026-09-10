import { expect, it } from "vitest"
import { transferInputs } from "./ledger-transfers"
import { accountPerspective } from "./flow-perspective"
const row = (
  key: string,
  account_id: string,
  direction: string,
  amount_minor: string,
  currency = "GBP"
) => ({
  key,
  case_id: "case",
  account_id,
  account_label: account_id,
  source_document_id: "source",
  direction,
  amount_minor,
  currency,
  ordering_date: "2026-01-01",
  description: "Synthetic",
})
const scope = transferInputs.parse({
  case_id: "case",
  start_date: null,
  end_date: null,
  population: "working",
  tolerance_days: 3,
  snapshot_sha256: "a".repeat(64),
  applied: false,
  limitation: "Conditional",
  excluded_rows: 0,
  date_unavailable_ids: [],
  rows: [
    row("in", "a", "credit", "9007199254740993"),
    row("d", "a", "debit", "100"),
    row("c", "b", "credit", "100"),
    row("out", "b", "debit", "30"),
    row("usd", "a", "credit", "50", "USD"),
  ],
  candidates: [
    {
      debit_id: "d",
      credit_id: "c",
      currency: "GBP",
      amount_minor: "100",
      outcome: "resolved",
      date_gap_days: 0,
      compared_date_field: "transaction_date",
    },
  ],
})
const pairs = [{ debit_id: "d", credit_id: "c" }]
it("counts internal pairs once and separates currencies without precision loss", () => {
  const result = accountPerspective(scope, ["a", "b"], pairs)
  expect(result.totals).toEqual([
    {
      currency: "GBP",
      incoming_minor: "9007199254740993",
      outgoing_minor: "30",
      internal_minor: "100",
      net_minor: "9007199254740963",
      internal_count: 1,
      movement_count: 3,
    },
    {
      currency: "USD",
      incoming_minor: "50",
      outgoing_minor: "0",
      internal_minor: "0",
      net_minor: "50",
      internal_count: 0,
      movement_count: 1,
    },
  ])
  expect(result.groups.flatMap((g) => g.transaction_ids)).not.toContain("d")
  expect(
    result.movements.find((m) => m.kind === "internal")?.transaction_ids
  ).toEqual(["d", "c"])
})
it("classifies the same pair differently from each selected account", () => {
  expect(
    accountPerspective(scope, ["a"], pairs).movements.find(
      (m) => m.transaction_ids.length === 2
    )?.kind
  ).toBe("outgoing")
  expect(
    accountPerspective(scope, ["b"], pairs).movements.find(
      (m) => m.transaction_ids.length === 2
    )?.kind
  ).toBe("incoming")
  expect(accountPerspective(scope, [], pairs).totals).toEqual([])
})
it("keeps both postings until an explicit pairing is applied and rejects source reuse", () => {
  expect(
    accountPerspective(scope, ["a", "b"], []).totals[0].internal_count
  ).toBe(0)
  expect(
    accountPerspective(scope, ["a", "b"], []).totals[0].outgoing_minor
  ).toBe("130")
  expect(() => accountPerspective(scope, ["a"], [...pairs, ...pairs])).toThrow(
    "reused"
  )
  expect(() => accountPerspective(scope, ["missing"], pairs)).toThrow(
    "distinct"
  )
})
