// Directed probing on the demo case (followups m111800442815723): six chains of four follow-ups an investigator would
// ask, each later question leaning on the earlier answer. Scores each step: the key's fact stated, citations given,
// the earlier answer carried (the step names what an earlier answer found, and does not ask the person to say it
// again), and decoys linked wrongly (planted-report-rubric.json). Never given to the agent.
import { expectHit } from "./demo-key-score.mjs"
import { scoreReport } from "./demo-report-score.mjs"

const ASKS_BACK = /\b(which (?:number|phone|person|one) do you mean|could you (?:clarify|specify)|please (?:specify|clarify|tell me which)|what do you mean by)\b/iu
const LINK = /\]\((?:rec|txn|doc|entity|evidence):\/\/[^)\s]+\)/gu

export function stepScore(step, answer, earlier = [], rubric = null) {
  const t = String(answer || "")
  const all = (step.expect?.all || []).every((w) => expectHit(w, t))
  const any = !step.expect?.any || step.expect.any.some((w) => expectHit(w, t))
  // carried: the step needs something only an earlier answer gave; it is carried when this answer names it, and the
  // run did not hand the question back
  const needs = (step.carries || []).filter((w) => earlier.some((e) => expectHit(w, e)))
  const carried = !ASKS_BACK.test(t) && (needs.length === 0 || needs.some((w) => expectHit(w, t)))
  const citations = (t.match(LINK) || []).length
  const decoys = rubric ? scoreReport(t, rubric).decoys.filter((d) => d.wrong).map((d) => d.id) : []
  return { fact: all && any, carried, citations, decoys }
}

export function chainScore(chain, answers, rubric = null) {
  const steps = chain.steps.map((s, i) => stepScore(s, answers[i], answers.slice(0, i), rubric))
  return { id: chain.id, steps, facts: steps.filter((s) => s.fact).length, carried: steps.filter((s) => s.carried).length,
           decoys: [...new Set(steps.flatMap((s) => s.decoys))] }
}

export function probingScore(chains, answersById, rubric = null) {
  const out = chains.map((c) => chainScore(c, answersById[c.id] || [], rubric))
  return { chains: out, facts: out.reduce((n, c) => n + c.facts, 0), carried: out.reduce((n, c) => n + c.carried, 0),
           of: chains.reduce((n, c) => n + c.steps.length, 0), decoys: [...new Set(out.flatMap((c) => c.decoys))] }
}
