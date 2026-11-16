// Scores one long report against evidence-engine/tests/phone/planted-report-rubric.json (lx-deepinvest A): which of the
// key's facts it states, which decoys it links (wrong), and the output defects that can be read from the text.
// Automatic first pass: the walk and the baseline table use it so every run is read the same way. Never given to the agent.
import { expectHit } from "./demo-key-score.mjs"

const sentences = (text) => String(text || "").split(/(?<=[.!?])\s+|\n+/u)

export function scoreReport(text, rubric) {
  const t = String(text || "")
  const facts = rubric.facts.map((f) => {
    const all = (f.all || []).every((w) => expectHit(w, t))
    const any = !f.any || f.any.some((w) => expectHit(w, t))
    return { id: f.id, found: all && any }
  })
  const decoys = rubric.decoys.map((d) => {
    const bad = sentences(t).some((s) => {
      const low = s.toLowerCase()
      return d.wrong.some((w) => new RegExp(w, "iu").test(low)) && !(d.explained || []).some((e) => new RegExp(e, "iu").test(low))
    })
    return { id: d.id, wrong: bad }
  })
  const dropped = sentences(t).filter((s) => new RegExp(rubric.defects.dropped_name, "iu").test(s)).length
  const heads = [...t.matchAll(/^\s{0,3}#{1,4}\s+(.+?)\s*#*\s*$/gmu)].map((m) => m[1].toLowerCase().replace(/[*_`]/g, "").trim())
  const duplicated = heads.filter((h, i) => heads.indexOf(h) !== i).length
  return {
    facts_found: facts.filter((f) => f.found).length,
    facts_of: facts.length,
    facts,
    decoys_wrong: decoys.filter((d) => d.wrong).length,
    decoys,
    defects: { dropped_names: dropped, duplicated_sections: duplicated },
  }
}
