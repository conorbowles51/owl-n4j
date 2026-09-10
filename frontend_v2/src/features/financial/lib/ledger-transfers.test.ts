import { expect, it } from "vitest"
import { transferInputs, verifyTransferScenario } from "./ledger-transfers"
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
    {
      key: "d",
      case_id: "case",
      account_id: "a",
      source_document_id: "s",
      amount_minor: "9007199254740993",
      currency: "GBP",
      direction: "debit",
      ordering_date: "2026-01-01",
      description: null,
    },
    {
      key: "c",
      case_id: "case",
      account_id: "b",
      source_document_id: "t",
      amount_minor: "9007199254740993",
      currency: "GBP",
      direction: "credit",
      ordering_date: "2026-01-01",
      description: null,
    },
  ],
  candidates: [
    {
      debit_id: "d",
      credit_id: "c",
      currency: "GBP",
      amount_minor: "9007199254740993",
      outcome: "resolved",
      date_gap_days: 0,
      compared_date_field: "transaction_date",
    },
  ],
})
const request = {
  pairs: [{ debit_id: "d", credit_id: "c" }],
  basis: "Source comparison",
  expected_snapshot_sha256: scope.snapshot_sha256,
}
async function report(amount = "9007199254740993") {
  const figures = [
    {
      currency: "GBP",
      posting_rows: 2,
      paired_transfers: 1,
      movement_count: 1,
      paired_amount_minor: amount,
      unpaired_credits_minor: "0",
      unpaired_debits_minor: "0",
      movement_volume_minor: amount,
    },
  ]
  const scenario_json = JSON.stringify({
    schema: "loupe.financial.transfer_scenario/1",
    case_id: "case",
    applied: false,
    pairings_verified: false,
    inputs: request,
    figures,
  })
  const bytes = new TextEncoder().encode(scenario_json)
  const scenario_sha256 = Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (b) => b.toString(16).padStart(2, "0")
  ).join("")
  return {
    case_id: "case",
    applied: false,
    figures,
    scenario_json,
    scenario_sha256,
    scenario_byte_count: bytes.length,
  }
}
it("independently reconciles selected source amounts without losing bigint precision", async () => {
  expect(
    (await verifyTransferScenario(await report(), scope, request)).figures[0]
      .movement_volume_minor
  ).toBe("9007199254740993")
})
it("rejects a hash-valid internally balanced report with the wrong money", async () => {
  await expect(
    verifyTransferScenario(await report("9007199254740992"), scope, request)
  ).rejects.toThrow("selected source readings")
})
