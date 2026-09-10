import { expect, it } from "vitest"
import { networkInputs, verifyNetworkTrace } from "./network-trace"
const row = (
  key: string,
  account_id: string,
  direction: string,
  amount_minor: string
) => ({
  key,
  case_id: "case",
  account_id,
  direction,
  amount_minor,
  currency: "GBP",
  source_document_id: "source-" + key,
  ordering_date: "2026-01-01",
  description: key,
})
export const scope = networkInputs.parse({
  case_id: "case",
  start_date: "2026-01-01",
  end_date: "2026-01-31",
  population: "working",
  tolerance_days: 3,
  snapshot_sha256: "a".repeat(64),
  applied: false,
  limitation: "Conditional",
  excluded_rows: 0,
  date_unavailable_ids: [],
  rows: [
    row("root", "a", "credit", "100"),
    row("debit", "a", "debit", "80"),
    row("credit", "b", "credit", "80"),
  ],
  candidates: [
    {
      debit_id: "debit",
      credit_id: "credit",
      currency: "GBP",
      amount_minor: "80",
      outcome: "resolved",
      date_gap_days: 0,
      compared_date_field: "transaction_date",
    },
  ],
  accounts: [
    { account_id: "a", currency: "GBP", label: "Account A" },
    { account_id: "b", currency: "GBP", label: "Account B" },
  ],
  network_row_limit: 300,
  network_limitation: "Forward assumptions",
})
const request = {
  expected_snapshot_sha256: scope.snapshot_sha256,
  currency: "GBP",
  ordered_transaction_ids: ["root", "debit", "credit"],
  doctrines: ["first_in_first_out"],
  openings: [{ account_id: "a" }, { account_id: "b" }],
  pairs: [{ debit_id: "debit", credit_id: "credit" }],
  attributions: [{ claim_id: "claim", amount_minor: "100" }],
}
const money = (minor_units: string) => ({ minor_units, currency: "GBP" })
async function report(remaining = "100", outside = "0") {
  const outcome = (
    deposited: string,
    surviving: string,
    withdrawn: string
  ) => ({
    currency: "GBP",
    closing_balance: money(surviving),
    lowest_balance: money("0"),
    notes: [],
    outcomes: {
      claim: {
        deposited: money(deposited),
        surviving: money(surviving),
        withdrawn: money(withdrawn),
      },
    },
  })
  const scenario_json = JSON.stringify({
    schema: "loupe.financial.network_trace/1",
    case_id: "case",
    applied: false,
    assumptions_verified: false,
    inputs: request,
    limitations: [],
    results: {
      first_in_first_out: {
        accounts: {
          a: outcome("100", "20", "80"),
          b: outcome("80", "80", "0"),
        },
        claims: {
          claim: {
            root_attributed_minor: "100",
            reported_remaining_minor: remaining,
            withdrawn_without_selected_transfer_minor: outside,
          },
        },
        unidentified_withdrawals_minor: "0",
        hops: [
          {
            debit_id: "debit",
            credit_id: "credit",
            from_account: "a",
            to_account: "b",
            amount_minor: "80",
            propagated_by_claim: { claim: "80" },
            unattributed_or_unidentified_minor: "0",
            unidentified_minor: "0",
            unfunded_minor: "0",
          },
        ],
      },
    },
  })
  const bytes = new TextEncoder().encode(scenario_json),
    scenario_sha256 = Array.from(
      new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
      (b) => b.toString(16).padStart(2, "0")
    ).join("")
  return {
    case_id: "case",
    applied: false,
    scenario_json,
    scenario_sha256,
    scenario_byte_count: bytes.length,
  }
}
it("verifies the source-linked transfer and per-account conservation", async () => {
  expect(
    (await verifyNetworkTrace(await report(), scope, request)).value.results
      .first_in_first_out.claims.claim.reported_remaining_minor
  ).toBe("100")
})
it("rejects internally balanced root figures that disagree with the account outcomes", async () => {
  await expect(
    verifyNetworkTrace(await report("99", "1"), scope, request)
  ).rejects.toThrow("conservation")
})

it("requires explicit backward assumptions and verifies dependency order and hop flags", async () => {
  const backward = {
    ...request,
    ordered_transaction_ids: ["credit", "root", "debit"],
    allow_backward: true,
    backward_basis: "Synthetic earlier receipt linked to later debit.",
  }
  async function capture(hopFlag = true, order = ["a", "b"]) {
    const original = await report(),
      doc = JSON.parse(original.scenario_json)
    doc.inputs = backward
    doc.backward_timing_used = true
    doc.calculation_account_order = order
    doc.results.first_in_first_out.hops[0].backward_timing = hopFlag
    const scenario_json = JSON.stringify(doc),
      bytes = new TextEncoder().encode(scenario_json)
    const scenario_sha256 = Array.from(
      new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
      (b) => b.toString(16).padStart(2, "0")
    ).join("")
    return {
      ...original,
      scenario_json,
      scenario_sha256,
      scenario_byte_count: bytes.length,
    }
  }
  expect(
    (await verifyNetworkTrace(await capture(), scope, backward)).value
      .backward_timing_used
  ).toBe(true)
  await expect(
    verifyNetworkTrace(await capture(false), scope, backward)
  ).rejects.toThrow("hop")
  await expect(
    verifyNetworkTrace(await capture(true, ["b", "a"]), scope, backward)
  ).rejects.toThrow("hop")
  await expect(
    verifyNetworkTrace(await capture(), scope, {
      ...backward,
      allow_backward: false,
    })
  ).rejects.toThrow("inputs")
})
