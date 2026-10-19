import { expect, it } from "vitest"
import { renderTraceReport } from "./trace-report"
import { traceFixture as fixture } from "./trace-fixture.test-support"
import { sha256Hex } from "@/lib/browser-crypto"

it("renders exact method results, source references and escaped evidence", async () => {
  const report = await renderTraceReport(await fixture())
  expect(report).toContain("90071992547409.93 GBP")
  expect(report).toContain("11111111-1111-4111-8111-111111111111 / 2")
  expect(report).toContain("&lt;script&gt;")
  expect(report).not.toContain("<script>")
  expect(report).not.toContain("<img ")
  expect(report).toContain("not the HTML report")
})
it("refuses changed bytes and renders the captured results rather than mutated display state", async () => {
  const trace = await fixture()
  if ("comparison" in trace.value)
    trace.value.comparison.results.first_in_first_out.outcomes.claim.surviving.minor_units =
      "1"
  expect(await renderTraceReport(trace)).toContain("90071992547409.93 GBP")
  trace.envelope.scenario_json += " "
  await expect(renderTraceReport(trace)).rejects.toThrow("changed")
})

it("splits other funds from unidentified and unfunded asset portions", async () => {
  const trace = await fixture()
  const captured = JSON.parse(trace.envelope.scenario_json)
  captured.asset_uses = {
    first_in_first_out: [
      {
        transaction_id: "source-row",
        asset_label: "Synthetic equipment",
        basis: "Synthetic report component check",
        amount_minor: "1200",
        currency: "GBP",
        allocated_by_claim: { claim: "100" },
        outside_claims_minor: "1100",
        unidentified_minor: "300",
        unfunded_minor: "200",
        changes_cash_results: false,
        limitation: "Synthetic display test only",
      },
    ],
  }
  trace.envelope.scenario_json = JSON.stringify(captured)
  const bytes = new TextEncoder().encode(trace.envelope.scenario_json)
  trace.envelope.scenario_sha256 = await sha256Hex(bytes)
  trace.envelope.scenario_byte_count = bytes.length
  const report = await renderTraceReport(trace)
  expect(report).toContain("<td>Other recorded funds</td><td>6.00 GBP</td>")
  expect(report).toContain("<td>Unidentified</td><td>3.00 GBP</td>")
  expect(report).toContain("<td>Unfunded</td><td>2.00 GBP</td>")
  expect(report).not.toContain("<td>Outside claims</td>")
})
