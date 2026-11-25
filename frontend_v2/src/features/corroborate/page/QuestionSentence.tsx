import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"
import { dossiersAPI } from "@/features/dossiers/api"
import { skippedWords, type RelationMember } from "@/features/relations/api"
import { corroborateAPI, scopeIsEmpty, type Preview, type Scope } from "../api"
import { openClaimComposer } from "../claim-composer"
import { QuestionMenu } from "../QuestionMenu"
import { removePart, type SelectionPart } from "../selection-store"
import type { Corroboration } from "../result-types"
import { names, RELATION_ORDER, RELATION_WORDS, template } from "./answer-model"

export interface Draft { kind: string; text: string; chips: Record<string, unknown>; /** The records inside the time scope, when one narrowed them. */ members?: RelationMember[] }
type Person = { key: string; label: string }
type Joined = { joined?: { people: Person[]; instances: string[] } }

const COMPARE: { key: string; words: string }[] = [
  { key: "same_people_ordinary", words: "the same hours on every other day" },
  { key: "same_weekday_hours", words: "the same weekday and hours in other weeks" },
]

/**
 * The question as a sentence (design screen 5): the people, the relation and the events are blue parts a person can
 * change. The relation swaps among the engine's question kinds in plain words; "test something someone said" opens
 * the free-text claim. Pressing Ask is the only thing that runs it.
 */
export function QuestionSentence({ caseId, members, sourceLabel, skipped, asked, busy, onAsk, parts, scope }: {
  caseId: string
  /** The screen's own time scope (a timeline range): the preview and the question keep to it. */
  scope?: Scope
  members: RelationMember[]
  sourceLabel: string
  skipped: { type: string; count: number }[]
  asked?: Corroboration
  busy: boolean
  onAsk: (d: Draft) => void
  /** The case-wide selection's parts, removable here; absent when the records came from one screen or an answer. */
  parts?: SelectionPart[]
}) {
  const key = members.map((m) => `${m.type}:${m.id}`).join("|")
  const preview = useQuery({
    queryKey: ["corroborate-preview", caseId, key, JSON.stringify(scope ?? {})],
    queryFn: () => corroborateAPI.preview(caseId, members, scope && !scopeIsEmpty(scope) ? scope : undefined) as Promise<Preview & Joined>,
    enabled: members.length > 0, staleTime: 30_000,
  })
  const taken: Person[] = useMemo(() => asked?.people.map((p) => ({ key: p.key, label: p.label })) ?? (preview.data?.joined?.people ?? preview.data?.taken.people)?.map((p) => ({ key: p.key, label: p.label })) ?? [], [asked, preview.data])
  const [people, setPeople] = useState<Person[] | null>(null)
  const [kind, setKind] = useState<string | null>(null)
  const [compare, setCompare] = useState<string | null>(null)
  const [after, setAfter] = useState<string>(typeof asked?.question.chips.after === "string" ? asked.question.chips.after : "")
  const [open, setOpen] = useState<"who" | "rel" | "events" | null>(null)
  const [menu, setMenu] = useState(false)
  const suggested = preview.data?.questions.map((q) => q.kind) ?? []
  const chosenKind = kind ?? asked?.question.kind ?? suggested[0] ?? "together"
  const who = people ?? taken
  const instances = asked ? asked.comparison.incident.length : preview.data?.joined?.instances.length ?? 0
  const events = asked?.days?.events_phrase ?? (instances === 1 ? "the day you chose" : instances ? `the ${instances} days you chose` : members.length ? "the records you chose" : "the days you choose")
  const { parts: sentence, rel } = template(chosenKind, who.length)
  const relWords = rel
  const picked = preview.data?.questions.find((q) => q.kind === chosenKind)
  const draft = (): Draft => ({
    kind: chosenKind,
    text: sentenceText(sentence, names(who.map((p) => p.label)), relWords, chosenKind === "behaviour_change" ? (after || "a date") : events),
    chips: {
      ...(picked?.chips ?? {}),
      people: who.map((p) => p.key),
      ...(compare ? { compare_with: compare } : asked?.question.chips.compare_with ? { compare_with: asked.question.chips.compare_with } : {}),
      ...(chosenKind === "behaviour_change" && after ? { after } : {}),
      ...(preview.data?.scope?.words.length ? { scope: preview.data.scope.words.join("; ") } : {}),
    },
    // inside the scope only: the preview named exactly which records are in it
    ...(preview.data?.scope?.kept ? { members: members.filter((m) => preview.data!.scope.kept!.some((k) => k.type === m.type && k.id === m.id)) } : {}),
  })
  const alternatives = [...new Set([...suggested, ...RELATION_ORDER])].filter((k) => k !== chosenKind && RELATION_WORDS[k])
  const canAsk = members.length > 0 && !busy && (chosenKind !== "behaviour_change" || !!after)
  return (
    <section aria-label="Your question" className="space-y-3 rounded-lg border bg-card p-4 sm:p-5" data-guide="corroborate-question">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Your question · click any blue part to change it</p>
      <div className="flex flex-wrap items-end gap-3">
        <p className="min-w-0 flex-1 text-xl leading-relaxed sm:text-2xl" data-testid="question-sentence">
          {sentence.map((s, i) => {
            if (s === "{who}") return <Part key={i} label="people" on={open === "who"} onClick={() => setOpen(open === "who" ? null : "who")}>{names(who.map((p) => p.label))}</Part>
            if (s === "{rel}") return <Part key={i} label="relation" on={open === "rel"} onClick={() => setOpen(open === "rel" ? null : "rel")}>{relWords}</Part>
            if (s === "{events}") return <Part key={i} label="events" on={open === "events"} onClick={() => setOpen(open === "events" ? null : "events")}>{chosenKind === "behaviour_change" ? (after || "a date you choose") : events}</Part>
            return <span key={i}>{s}</span>
          })}
        </p>
        <Button disabled={!canAsk} onClick={() => onAsk(draft())} data-guide="corroborate-ask">{busy ? "Starting…" : asked ? "Ask again" : "Ask"}</Button>
      </div>
      {open === "who" && <PeopleEditor caseId={caseId} who={who} onChange={setPeople} />}
      {open === "rel" && (
        <div role="radiogroup" aria-label="What to test" className="flex flex-wrap gap-2 rounded border p-2">
          {[chosenKind, ...alternatives].map((k) => (
            <label key={k} className={cn("cursor-pointer rounded-full border px-3 py-1 text-sm", k === chosenKind && "border-status-info bg-status-info-soft")}>
              <input type="radio" className="sr-only" name="corro-relation" checked={k === chosenKind} onChange={() => { setKind(k); setOpen(null) }} />
              {RELATION_WORDS[k]}
            </label>
          ))}
        </div>
      )}
      {open === "events" && (
        <div className="space-y-2 rounded border p-3 text-sm">
          {chosenKind === "behaviour_change" ? (
            <label className="flex items-center gap-2">The date to compare before and after
              <input type="date" className="rounded border bg-background px-2 py-1" value={after} onChange={(e) => setAfter(e.target.value)} />
            </label>
          ) : (
            <>
              <p className="font-medium">{instances ? `${instances} day${instances === 1 ? "" : "s"} asked about` : "No dated records chosen yet"}{sourceLabel ? `, from ${sourceLabel}` : ""}</p>
              {(asked ? asked.comparison.incident.map((i) => i.label) : preview.data?.joined?.instances ?? []).length > 0 && (
                <ul className="flex flex-wrap gap-1 text-xs">{(asked ? asked.comparison.incident.map((i) => i.label) : preview.data?.joined?.instances ?? []).map((d) => <li key={d} className="rounded bg-muted px-2 py-0.5">{d}</li>)}</ul>
              )}
              {parts && parts.length > 0 && (
                <ul className="space-y-1" aria-label="What you chose">
                  {parts.map((p) => <li key={p.id} className="flex items-center gap-2">{p.label} <span className="text-muted-foreground">from {p.screen}</span><button type="button" className="text-xs underline" onClick={() => removePart(caseId, p.id)}>Remove</button></li>)}
                </ul>
              )}
              <label className="flex flex-wrap items-center gap-2">Compared with
                <select className="rounded border bg-background px-2 py-1" value={compare ?? (typeof asked?.question.chips.compare_with === "string" ? asked.question.chips.compare_with : "same_people_ordinary")} onChange={(e) => setCompare(e.target.value)}>
                  {COMPARE.map((c) => <option key={c.key} value={c.key}>{c.words}</option>)}
                </select>
              </label>
              {parts && parts.length > 0 && <button type="button" className="text-xs text-status-info underline" onClick={() => setMenu(true)}>Narrow to a time window, or ask about each group in turn</button>}
            </>
          )}
        </div>
      )}
      {alternatives.length > 0 && (
        <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span>Instead of “{relWords}”:</span>
          {alternatives.slice(0, 5).map((k) => <button key={k} type="button" className="rounded-full border px-2.5 py-0.5 text-sm text-status-info hover:bg-muted" onClick={() => setKind(k)}>{RELATION_WORDS[k]}</button>)}
        </p>
      )}
      {preview.isLoading && <p role="status" className="text-sm text-muted-foreground">Reading what you chose…</p>}
      {preview.isError && <p role="alert" className="text-sm text-status-error">What you chose could not be read. Choose the records again on their screen and press Corroborate.</p>}
      {skipped.length > 0 && <p role="status" className="text-sm text-muted-foreground">{skippedWords(skipped, members.length === 0)}</p>}
      {members.length === 0 && <p className="text-sm">Nothing is chosen to ask about yet.</p>}
      {!!preview.data?.scope?.words.length && <p role="status" className="text-sm">Kept to {preview.data.scope.words.join("; ")}{preview.data.scope.outside_total ? `: ${preview.data.scope.outside_total.toLocaleString("en-US")} chosen records fall outside it and are left out` : ""}.</p>}
      <p className="text-sm text-muted-foreground">
        How you get here: select records, people or a payment anywhere in Loupe (a message, a row in the ledger, a document, a day on the timeline) and press <strong className="text-foreground">Corroborate</strong>. Loupe fills in the question from what you selected. You can also{" "}
        <button type="button" className="text-status-info underline" onClick={() => openClaimComposer({ text: "" })}>test something someone said</button> in their own words.
      </p>
      {menu && <QuestionMenu caseId={caseId} onClose={() => setMenu(false)} />}
    </section>
  )
}

function sentenceText(parts: string[], who: string, rel: string, events: string): string {
  return parts.map((p) => (p === "{who}" ? who : p === "{rel}" ? rel : p === "{events}" ? events : p)).join("")
}

function Part({ children, on, onClick, label }: { children: React.ReactNode; on: boolean; onClick: () => void; label: string }) {
  return (
    <button type="button" aria-expanded={on} aria-label={`Change the ${label}: ${typeof children === "string" ? children : ""}`} onClick={onClick}
      className={cn("rounded px-1 font-semibold text-status-info underline decoration-dotted underline-offset-4 hover:bg-status-info-soft", on && "bg-status-info-soft")}>
      {children}
    </button>
  )
}

function PeopleEditor({ caseId, who, onChange }: { caseId: string; who: Person[]; onChange: (p: Person[]) => void }) {
  const [find, setFind] = useState("")
  const list = useQuery({ queryKey: ["dossiers", caseId, "corroborate", find], queryFn: () => dossiersAPI.list({ caseId, q: find || undefined, limit: 20 }), staleTime: 30_000 })
  const keys = new Set(who.map((p) => p.key))
  return (
    <div className="space-y-2 rounded border p-3 text-sm">
      <ul className="flex flex-wrap gap-2" aria-label="People asked about">
        {who.map((p) => <li key={p.key} className="flex items-center gap-1 rounded-full border px-2 py-0.5">{p.label}<button type="button" aria-label={`Remove ${p.label}`} className="text-muted-foreground" onClick={() => onChange(who.filter((x) => x.key !== p.key))}>×</button></li>)}
        {who.length === 0 && <li className="text-muted-foreground">Nobody yet. Loupe asks about the people the records name.</li>}
      </ul>
      <label className="flex flex-wrap items-center gap-2">Add someone
        <input className="rounded border bg-background px-2 py-1" placeholder="Name" value={find} onChange={(e) => setFind(e.target.value)} />
      </label>
      {list.data && (
        <ul className="flex flex-wrap gap-1">
          {list.data.dossiers.filter((d) => !keys.has(`person:${d.id}`)).slice(0, 12).map((d) => (
            <li key={d.id}><button type="button" className="rounded-full border px-2 py-0.5 text-status-info hover:bg-muted" onClick={() => onChange([...who, { key: `person:${d.id}`, label: d.display_name }])}>+ {d.display_name}</button></li>
          ))}
        </ul>
      )}
      {list.isError && <p role="alert" className="text-status-error">The people in this case could not be read.</p>}
    </div>
  )
}
