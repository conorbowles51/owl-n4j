import { webcrypto } from "node:crypto"
import { describe, it, expect, vi } from "vitest"
import { traceInputs, verifyTraceResponse } from "./ledger-trace"
vi.stubGlobal("crypto", webcrypto)
const scope = traceInputs.parse({
  case_id: "case",
  account_id: "account",
  start_date: "2026-01-01",
  end_date: "2026-01-31",
  currency: "GBP",
  snapshot_sha256: "a".repeat(64),
  included_rows: 1,
  excluded_rows: 0,
  applied: false,
  readings: [
    {
      included: true,
      row: {
        key: "row",
        ordering_date: "2026-01-01",
        amount_minor: "9007199254740993",
        direction: "credit",
        description: "Deposit",
        currency: "GBP",
      },
    },
  ],
})
const request = {
  expected_snapshot_sha256: scope.snapshot_sha256,
  attributions: [
    {
      transaction_id: "row",
      amount_minor: "9007199254740993",
      basis: "Document",
    },
  ],
}
async function fixture(patch = {}) {
  const scenario_json = JSON.stringify({
    schema: "loupe.financial.conditional_trace/1",
    case_id: "case",
    account_id: "account",
    applied: false,
    assumptions_verified: false,
    inputs: {
      ...request,
      attributions: [
        {
          basis: "Document",
          amount_minor: "9007199254740993",
          transaction_id: "row",
        },
      ],
    },
    limitations: ["Conditional"],
    comparison: { results: {} },
    ...patch,
  })
  const bytes = new TextEncoder().encode(scenario_json)
  const scenario_sha256 = Buffer.from(
    await webcrypto.subtle.digest("SHA-256", bytes)
  ).toString("hex")
  return {
    case_id: "case",
    account_id: "account",
    applied: false,
    scenario_json,
    scenario_sha256,
    scenario_byte_count: bytes.length,
  }
}
describe("trace contracts", () => {
  it("refuses missing selected methods", async () => {
    const requested = { ...request, doctrines: ["first_in_first_out"] }
    await expect(
      verifyTraceResponse(
        await fixture({ inputs: requested }),
        scope,
        requested
      )
    ).rejects.toThrow("different calculation methods")
  })

  it("preserves exact download bytes and compares assumptions independent of JSON key order", async () => {
    const raw = await fixture()
    expect(
      (await verifyTraceResponse(raw, scope, request)).envelope.scenario_json
    ).toBe(raw.scenario_json)
  })
  it("refuses corrupted bytes", async () => {
    const raw = await fixture()
    await expect(
      verifyTraceResponse(
        { ...raw, scenario_json: raw.scenario_json + " " },
        scope,
        request
      )
    ).rejects.toThrow("integrity")
  })
  it.each([
    { case_id: "other" },
    { account_id: "other" },
    { inputs: { ...request, expected_snapshot_sha256: "b".repeat(64) } },
    { inputs: { ...request, attributions: [] } },
  ])("refuses wrong scope or assumptions %s", async (patch) => {
    await expect(
      verifyTraceResponse(await fixture(patch), scope, request)
    ).rejects.toThrow("match")
  })
  it("refuses duplicate, missing and mixed currency rows", () => {
    expect(
      traceInputs.safeParse({
        ...scope,
        included_rows: 2,
        readings: [...scope.readings, ...scope.readings],
      }).success
    ).toBe(false)
    expect(traceInputs.safeParse({ ...scope, included_rows: 2 }).success).toBe(
      false
    )
    expect(traceInputs.safeParse({ ...scope, currency: "USD" }).success).toBe(
      false
    )
  })
})
