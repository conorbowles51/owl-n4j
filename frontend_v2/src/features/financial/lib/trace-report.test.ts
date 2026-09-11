import { expect, it } from "vitest"
import { renderTraceReport } from "./trace-report"
import { traceFixture as fixture } from "./trace-fixture.test-support"

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
