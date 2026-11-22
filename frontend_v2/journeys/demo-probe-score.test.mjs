// node --test journeys/demo-probe-score.test.mjs
import { test } from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { chainScore, stepScore } from "./demo-probe-score.mjs"

const chains = JSON.parse(readFileSync(new URL("./demo-probe-chains.json", import.meta.url))).chains

test("six chains of four follow-ups, every later step leaning on an earlier answer", () => {
  assert.equal(chains.length, 6)
  for (const c of chains) {
    assert.equal(c.steps.length, 4)
    for (const s of c.steps.slice(1)) assert.ok(s.carries?.length, `${c.id}: "${s.q}" names what it carries`)
  }
})

test("step 3 that needs step 2's answer: carried when it names it, not when it asks again or drifts", () => {
  const p3 = chains.find((c) => c.id === "P3")
  const earlier = ["The message 'I left something in the tow truck, need it back' is on Kell's phone.",
                   "Travis Kell sent it to Desmond Okafor; Kell's copy was deleted."]
  const good = stepScore(p3.steps[2], "Kell meant the second phone, the prepaid one in the glovebox [rec](rec://a1).", earlier)
  assert.deepEqual({ fact: good.fact, carried: good.carried, citations: good.citations }, { fact: true, carried: true, citations: 1 })
  const asks = stepScore(p3.steps[2], "Which phone do you mean? Could you clarify who sent it?", earlier)
  assert.equal(asks.carried, false)
  const drift = stepScore(p3.steps[2], "Tow trucks often carry a spare phone in the glovebox.", earlier)
  assert.equal(drift.carried, false)
})

test("a chain scores facts and carried steps", () => {
  const p2 = chains.find((c) => c.id === "P2")
  const s = chainScore(p2, ["Mateo was with Vint's tow on 12-13 April.", "N3: Mateo was at the ER at Ferrowmere.",
    "The Ferrowmere discharge paper says Discharged 4 May 2024 03:38.", "Mateo's phone has no contact with Desmond Okafor."])
  assert.equal(s.facts, 4)
  assert.equal(s.carried, 4)
})

test("chain keys follow the planted truths: Kell sent the tow-truck message; Okafor's badge was not at dock 3", () => {
  // Fails on the chains before: P3 step 2 wanted Okafor as the sender and P6 step 3 asked for a second badge at dock 3
  const p3 = chains.find((c) => c.id === "P3"), p6 = chains.find((c) => c.id === "P6")
  const kellSent = "Travis Kell (@tk_nights) sent it to Desmond Okafor; Kell's copy is a recovered deleted message."
  assert.equal(stepScore(p3.steps[1], kellSent, ["left something in the tow truck"]).fact, true)
  assert.equal(stepScore(p3.steps[1], "Desmond Okafor deleted it.", ["left something in the tow truck"]).fact, false)
  assert.ok(!/same door/u.test(p6.steps[2].q))
})
