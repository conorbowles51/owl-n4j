// node --test journeys/demo-key-score.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { expectHit } from "./demo-key-score.mjs"

const { cases } = JSON.parse(readFileSync(new URL("./demo-key-score-cases.json", import.meta.url)))

test("each shared case scores as written", () => {
  for (const c of cases) assert.equal(expectHit(c.term, c.text), c.hit, `${c.term} in ${c.text}`)
})
