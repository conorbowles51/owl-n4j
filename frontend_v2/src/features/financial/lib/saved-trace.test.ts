import { expect, it } from "vitest"
import { traceFixture } from "./trace-fixture.test-support"
import { readSavedTrace, traceFindingLinks } from "./saved-trace"
it("saves the full calculation with only its linked source payments and restores exact results", async () => {
  const trace = await traceFixture(),
    links = await traceFindingLinks(trace)
  expect(links).toHaveLength(1)
  expect(links[0].source_anchor?.financial_transaction_ids).toEqual([
    "source-row",
  ])
  expect(links[0].metadata?.envelope).toEqual(trace.envelope)
  const restored = await readSavedTrace(links[0].metadata?.envelope, "case")
  expect(restored.value).toEqual(trace.value)
})
it("rejects changed bytes and a different case before opening saved results", async () => {
  const trace = await traceFixture()
  await expect(readSavedTrace(trace.envelope, "other")).rejects.toThrow(
    "another case"
  )
  await expect(
    readSavedTrace(
      { ...trace.envelope, scenario_json: trace.envelope.scenario_json + " " },
      "case"
    )
  ).rejects.toThrow("changed")
})
