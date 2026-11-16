// node --test journeys/demo-report-score.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { scoreReport } from "./demo-report-score.mjs"

const rubric = JSON.parse(readFileSync(new URL("../../evidence-engine/tests/phone/planted-report-rubric.json", import.meta.url)))

test("facts need all their terms and one of the any terms", () => {
  const s = scoreReport("Okafor's phone holds no contact with Mateo's. Penn got a price list. The B-20417 badge was in.", rubric)
  const ids = s.facts.filter((f) => f.found).map((f) => f.id)
  assert.deepEqual(ids.sort(), ["F05", "F13", "F23"])
})

test("a decoy linked without an explanation is wrong; explained it is not", () => {
  assert.equal(scoreReport("Carla Ruiz is related to Mateo Ruiz.", rubric).decoys_wrong, 1)
  assert.equal(scoreReport("Carla Ruiz is unrelated to Mateo Ruiz.", rubric).decoys_wrong, 0)
  assert.equal(scoreReport("Curtis Fallowby is the user of the glovebox phone.", rubric).decoys_wrong, 1)
  assert.equal(scoreReport("Curtis Fallowby was its 2022 owner, a recycled number.", rubric).decoys_wrong, 0)
})

test("dropped names and doubled sections are counted", () => {
  const s = scoreReport("Copies appear on and .\n\n## Open questions\nx\n## Open questions\ny\n", rubric)
  assert.equal(s.defects.dropped_names, 1)
  assert.equal(s.defects.duplicated_sections, 1)
})
