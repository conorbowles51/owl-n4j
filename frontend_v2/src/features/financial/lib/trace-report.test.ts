import { expect, it } from "vitest"
import { traceScenarioSchema } from "./ledger-trace"
import { renderTraceReport, type VerifiedTrace } from "./trace-report"
async function fixture(): Promise<VerifiedTrace> {
  const money = (minor_units: string) => ({ minor_units, currency: "GBP" })
  const captured = {
    schema: "loupe.financial.conditional_trace/1",
    case_id: "case",
    account_id: "account",
    applied: false,
    assumptions_verified: false,
    inputs: { expected_snapshot_sha256: "a".repeat(64) },
    limitations: ["<script>unsafe</script>"],
    comparison: {
      results: {
        first_in_first_out: {
          outcomes: {
            claim: {
              deposited: money("9007199254740993"),
              surviving: money("9007199254740993"),
              withdrawn: money("0"),
            },
          },
          draws: [],
          notes: ["Conditional"],
        },
      },
    },
    ledger_snapshot: {
      ledger: {
        case_id: "case",
        readings: [
          {
            row: {
              key: "source-row",
              ordering_date: "2026-01-01",
              description: "<img src=x onerror=evil()>",
              amount_minor: "9007199254740993",
              currency: "GBP",
              proof_class: "p3",
              locator: { page: 2 },
            },
            source: {
              id: "source-document",
              evidence_file_id: "source-file",
              sha256_at_ingestion: "b".repeat(64),
            },
          },
        ],
      },
    },
  }
  const scenario_json = JSON.stringify(captured),
    bytes = new TextEncoder().encode(scenario_json)
  const scenario_sha256 = Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (b) => b.toString(16).padStart(2, "0")
  ).join("")
  return {
    envelope: {
      case_id: "case",
      account_id: "account",
      applied: false,
      scenario_json,
      scenario_sha256,
      scenario_byte_count: bytes.length,
    },
    value: traceScenarioSchema.parse(captured),
  }
}
it("renders exact method results, source references and escaped evidence", async () => {
  const report = await renderTraceReport(await fixture())
  expect(report).toContain("90071992547409.93 GBP")
  expect(report).toContain("source-file / 2")
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
