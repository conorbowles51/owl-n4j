// node --test journeys/demo-key-score.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { expectHit, wrongWords } from "./demo-key-score.mjs"

const { cases } = JSON.parse(readFileSync(new URL("./demo-key-score-cases.json", import.meta.url)))

test("each shared case scores as written", () => {
  for (const c of cases) assert.equal(expectHit(c.term, c.text), c.hit, `${c.term} in ${c.text}`)
})

const { wrong_cases: wrongCases } = JSON.parse(readFileSync(new URL("./demo-key-score-cases.json", import.meta.url)))

test("a wrong word in the labelled other version is not a wrong answer; anywhere else it is", () => {
  for (const c of wrongCases) assert.deepEqual(wrongWords(c.must_not, c.text), c.wrong, c.text)
})
