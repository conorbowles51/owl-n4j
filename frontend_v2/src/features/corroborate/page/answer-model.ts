import type { Check, Corroboration, DayTile } from "../result-types"

/**
 * The Corroborate page's words (lx-corroredo, design screen 5), computed from the engine's result by rule. Nothing
 * here is written by a model; every sentence is built from the result's own counts, days and checks.
 */

/** The relation part of the question sentence, per question kind, in plain words. */
export const RELATION_WORDS: Record<string, string> = {
  together: "together",
  in_contact: "in contact",
  payment: "paying each other",
  every_time: "doing this every time",
  who_else: "with anyone else",
  connected: "connected at all",
  behaviour_change: "behaving differently after a date",
  statement: "as someone said",
  who_used: "using this phone",
  document: "as the document says",
}

/** The kinds offered in the "Instead of" line, most asked first. */
export const RELATION_ORDER = ["together", "in_contact", "payment", "every_time", "who_else", "connected", "behaviour_change", "document", "who_used"]

export function names(labels: string[]): string {
  if (!labels.length) return "these people"
  if (labels.length === 1) return labels[0]
  return `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`
}

/** The question as a sentence, per kind: {who}, {rel} and {events} are the parts a person can change. */
export const TEMPLATES: Record<string, { text: string; rel: string }> = {
  together: { text: "Were {who} {rel} on {events}?", rel: "together" },
  in_contact: { text: "Were {who} {rel} on {events}?", rel: "in contact" },
  payment: { text: "Were {who} {rel} around {events}?", rel: "paying each other" },
  every_time: { text: "Are {who} {rel}, as on {events}?", rel: "doing this every time" },
  who_else: { text: "Was anyone else {rel} {who} on {events}?", rel: "with" },
  connected: { text: "Is {who} {rel} to the others on {events}?", rel: "connected at all" },
  behaviour_change: { text: "Did {who} {rel} after {events}?", rel: "behave differently" },
  statement: { text: "Do the records of {who} fit {rel} on {events}?", rel: "what was said" },
  who_used: { text: "{rel} the phone of {who}?", rel: "Who used" },
  document: { text: "Do the phones of {who} {rel}?", rel: "agree with the document" },
}

/** One-person questions read "Was", not "Were". */
export function template(kind: string, people: number): { parts: string[]; rel: string } {
  const t = TEMPLATES[kind] ?? TEMPLATES.together
  const text = people === 1 ? t.text.replace(/^Were /, "Was ").replace(/^Are /, "Is ") : t.text
  return { parts: text.split(/(\{who\}|\{rel\}|\{events\})/).filter(Boolean), rel: t.rel }
}

/** What the level means, in the design's words: a likelihood, never a yes or no. */
export const LEVEL_GLOSS: Record<string, string> = {
  strong: "very unlikely to be chance, but still not proof",
  probable: "well above chance, but not proven",
  possible: "more than chance alone would give, but weak",
  cant_tell: "the records cannot settle it either way",
  coincidence: "about what chance alone would give",
  no_link_found: "nothing links them in the records searched",
}
export const SCALE: { key: string; name: string }[] = [
  { key: "coincidence", name: "Coincidence likely" },
  { key: "cant_tell", name: "Can't tell" },
  { key: "possible", name: "Possible" },
  { key: "probable", name: "Probable" },
  { key: "strong", name: "Strong" },
]

/** The innocent explanation each check tests, asked as a plain question a reader would raise. */
export const INNOCENT: Record<string, string> = {
  routine: "They are simply in touch all the time.",
  household: "They live together.",
  workplace: "They work together, so of course they meet.",
  stock_phrase: "It is a common phrase that many people use.",
  busy_place: "Their routes just cross somewhere busy.",
  clock_zone: "A phone's clock or time zone is off.",
  recycled_number: "The number belonged to someone else at the time.",
  same_name: "It is a different person with the same name.",
  shared_device: "One person carries both phones.",
  duplicate_copy: "The same record is counted more than once.",
  received_media: "A photo someone sent shows a place they never went.",
}
/** A check that a person can settle by recording a case fact, with the fact's kind. */
export const FACT_FOR: Record<string, { kind: string; words: string; ifSo: string }> = {
  household: { kind: "live_together", words: "They live together", ifSo: "If they live together, being in the same place tells you little: those days would count for less." },
  workplace: { kind: "work_group", words: "They work together", ifSo: "If they work together, meeting in work hours would count for less." },
}

/** An explanation a case fact would settle: the records neither ruled it out nor weighed it in. */
function unsettled(k: Check): boolean { return k.outcome === "checked" || k.outcome === "no_data" }

export type Pill = "Ruled out" | "Counts for less" | "Not known" | "Did not arise"
export function pill(c: Check): Pill {
  if (c.outcome === "ruled_out") return "Ruled out"
  if (c.outcome === "weighed_low") return "Counts for less"
  if (c.outcome === "no_data" || c.open) return "Not known"
  return "Did not arise"
}
const PILL_RANK: Record<Pill, number> = { "Ruled out": 0, "Counts for less": 1, "Not known": 2, "Did not arise": 3 }

export interface Innocent { check: string; question: string; pill: Pill; words: string; records: string[]; fact?: { kind: string; words: string } }
export function innocentExplanations(c: Corroboration): Innocent[] {
  return c.checks
    .map((k) => ({ check: k.check, question: INNOCENT[k.check] ?? k.words, pill: pill(k), words: k.words, records: k.records ?? [],
                   ...(FACT_FOR[k.check] && unsettled(k) ? { fact: { kind: FACT_FOR[k.check].kind, words: FACT_FOR[k.check].words } } : {}) }))
    .sort((a, b) => PILL_RANK[a.pill] - PILL_RANK[b.pill])
}

/** How many of the days asked about the relation held on, and on how many it could be read. */
export function tally(tiles: DayTile[]): { present: number; absent: number; no_data: number; of: number } {
  const t = { present: 0, absent: 0, no_data: 0, of: tiles.length }
  for (const x of tiles) t[x.outcome] += 1
  return t
}

/** "What would change the answer": each day the records do not cover, each gap, each innocent explanation a case fact would settle. */
export function changes(c: Corroboration): { text: string; fact?: { kind: string; words: string } }[] {
  const out: { text: string; fact?: { kind: string; words: string } }[] = []
  const d = c.days
  if (d?.relation) {
    const t = tally(d.tiles)
    for (const tile of d.tiles.filter((x) => x.outcome === "no_data")) {
      out.push({ text: `${tile.date}: ${tile.detail} If anything in the case shows them ${d.relation.word} that day, this becomes ${t.present + 1} of ${t.of}.` })
    }
    if (t.no_data === 0 && t.absent > 0 && t.absent <= 2) {
      for (const tile of d.tiles.filter((x) => x.outcome === "absent"))
        out.push({ text: `${tile.date} is a day asked about when they look not ${d.relation.word}. Records from another source for that day (calls, card payments, photos) could show otherwise.` })
    }
  }
  for (const g of c.gaps) out.push({ text: g.words })
  const used = new Set((c as { case_facts_used?: { kind: string }[] }).case_facts_used?.map((f) => f.kind) ?? [])
  for (const k of c.checks) {
    const f = FACT_FOR[k.check]
    if (f && unsettled(k) && !used.has(f.kind) && (c.people?.length ?? 0) >= 2)
      out.push({ text: `${f.ifSo} Nobody has recorded this in the case.`, fact: { kind: f.kind, words: f.words } })
  }
  return out
}

export interface NextStep {
  title: string
  why: string
  action: string
  /** A page to open, with the people and days filled in. */
  to?: string
  /** Or a new question to ask on this page. */
  ask?: { kind: string; chips: Record<string, unknown> }
}

function day(iso: string): string { return iso.slice(0, 10) }
function windowQuery(from: string, to: string): string { return `window=${encodeURIComponent(`${from}..${to}`)}` }

/**
 * Ranked next steps (COMMON rule 4), each built from this result's own data: the days the records do not cover, the
 * contact between the people on the days asked about, an innocent explanation nobody has settled, other people with
 * links on those days, the meeting places, and the engine's own further questions. Never a fixed list: a step whose
 * data is not in the result is not offered.
 */
export function nextSteps(c: Corroboration, caseId: string): NextStep[] {
  const base = `/cases/${encodeURIComponent(caseId)}`
  const steps: NextStep[] = []
  const d = c.days
  const who = names(c.people.map((p) => p.label))
  const peopleKeys = c.people.map((p) => p.key)
  const incidents = c.comparison.incident
  const first = incidents.length ? day(incidents[0].start) : ""
  const last = incidents.length ? day(incidents[incidents.length - 1].end) : ""
  // 1. the days asked about that the records do not cover, or where the relation did not hold
  for (const t of (d?.tiles ?? []).filter((x) => x.outcome !== "present").slice(0, 2)) {
    steps.push({
      title: `Fill the gap on ${t.date}`,
      why: `${t.outcome === "no_data" ? t.detail : `The records show them not ${d?.relation?.word ?? "linked"} that day.`} Every other source for that day (calls, card payments, photos, places) is on the timeline.`,
      action: "Search that day", to: `${base}/timeline?${windowQuery(t.instance, t.instance)}`,
    })
  }
  // 2. what they said to each other on the days asked about
  const contact = c.grid.filter((r) => r.link_kind === "contact" && !r.context)
  const ids = new Set(incidents.map((i) => i.id))
  let n = 0
  let on = 0
  for (const r of contact) {
    let rowDays = 0
    for (const [inst, cnt] of Object.entries(r.record_counts ?? {})) if (ids.has(inst)) { n += cnt; rowDays += 1 }
    on = Math.max(on, rowDays)
  }
  if (n > 0 && first)
    steps.push({ title: "Read what they said to each other on those days",
                 why: `${n.toLocaleString("en-US")} call${n === 1 ? "" : "s"}, message${n === 1 ? "" : "s"} or e-mail${n === 1 ? "" : "s"} between ${who} on ${on} of the ${incidents.length} day${incidents.length === 1 ? "" : "s"} asked about.`,
                 action: "Open their messages", to: `${base}/conversations?${windowQuery(first, last)}` })
  // 3. an innocent explanation a case fact would settle
  const unsettled = changes(c).find((x) => x.fact)
  if (unsettled?.fact)
    steps.push({ title: `Settle whether ${unsettled.fact.words.charAt(0).toLowerCase()}${unsettled.fact.words.slice(1)}`,
                 why: `The one innocent explanation the records cannot test. Their addresses or workplaces may be in the documents or interview notes.`,
                 action: "Search the documents", to: `${base}/search?q=${encodeURIComponent(c.people.map((p) => p.label).join(" "))}` })
  // 4. other people with links on those days
  for (const o of c.not_in_pattern.filter((x) => (x.found?.length ?? 0) > 0 && x.key).slice(0, 2)) {
    steps.push({ title: `Ask about ${o.who} on those days`,
                 why: `${o.says}. Corroborate can weigh ${o.who} with ${who} on the same days.`,
                 action: `Ask about ${o.who}`, ask: { kind: c.question.kind, chips: { ...c.question.chips, people: [...peopleKeys, o.key] } } })
  }
  // 5. where they were together
  const met = c.grid.find((r) => r.link_kind === "together" && r.incident.present > 0 && !r.context)
  if (met && first)
    steps.push({ title: "See where they met", why: `${met.label} on ${met.incident.present} of the ${met.incident.of} day${met.incident.of === 1 ? "" : "s"} asked about, on the map with the times.`,
                 action: "Open on the map", to: `${base}/map?${windowQuery(first, last)}` })
  // 6. does it happen every time
  if (c.question.kind !== "every_time" && incidents.length >= 1 && c.question.kind !== "who_used")
    steps.push({ title: "Test whether this happens every time",
                 why: `${incidents.length} day${incidents.length === 1 ? "" : "s"} asked about. Loupe can look for every other day with the same links at the same hours.`,
                 action: "Does this happen every time?", ask: { kind: "every_time", chips: { people: peopleKeys } } })
  // 7. the engine's own further questions
  for (const l of c.look_further.slice(0, 2))
    steps.push({ title: l.text, why: `${l.count.toLocaleString("en-US")} record${l.count === 1 ? "" : "s"} or people in the case for this question.`, action: "Ask this", ask: l.question })
  return steps
}

/** A sentence that opens with a name such as "the user of Phone 3" starts with a capital, as any sentence does. */
export function opening(text: string): string {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text
}
