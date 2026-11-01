import { useEffect, useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { register } from "@/lib/keymap"
import { messageView, type FixtureCase, type FixtureMessage } from "../fixtures"
import { participantsLine } from "../types"
import { instantWords } from "../lib/time-words"
import { fmt } from "../ui/ResultCount"

/**
 * Prototype: Needs a decision, readings group (07 J-8): readings grouped by phone and type, ordered by records
 * affected, each a plain sentence; examples drawn from the whole set covering every kind present; Looks right
 * disabled until every kind has been shown; y / x / s; a standard reason is recorded and labelled as such.
 * Synthetic data; nothing is saved.
 */
interface Reading {
  id: string
  phone: string
  app: string
  sentence: string
  affected: FixtureMessage[]
  kinds: { kind: string; example: FixtureMessage }[]
}

function kindsOf(fx: FixtureCase, ms: FixtureMessage[]) {
  const groups = new Set(fx.threads.filter((t) => t.group).map((t) => t.id))
  const pick = (label: string, test: (m: FixtureMessage) => boolean) => {
    const found = ms.find(test)
    return found ? [{ kind: label, example: found }] : []
  }
  return [
    ...pick("Incoming, one to one", (m) => m.direction === "incoming" && !groups.has(m.thread) && !!m.body),
    ...pick("Outgoing, one to one", (m) => m.direction === "outgoing" && !groups.has(m.thread) && !!m.body),
    ...pick("Group message", (m) => groups.has(m.thread)),
    ...pick("Empty text", (m) => !m.body),
    ...pick("No time", (m) => !m.time),
  ]
}

export function readingsFor(fx: FixtureCase): Reading[] {
  const out: Reading[] = []
  for (const p of fx.phones) {
    const byApp = new Map<string, FixtureMessage[]>()
    for (const m of fx.messages) if (m.phone === p.label) byApp.set(m.app, [...(byApp.get(m.app) ?? []), m])
    for (const [app, ms] of byApp) {
      out.push({
        id: `${p.label}-${app}`,
        phone: p.label,
        app,
        sentence: `On ${p.label}, ${app} messages: the From field is read as the sender. Affects ${fmt(ms.length)} messages.`,
        affected: ms,
        kinds: kindsOf(fx, ms),
      })
    }
  }
  return out.sort((a, b) => b.affected.length - a.affected.length)
}

type Outcome = { kind: "confirmed" | "not-right" | "skipped"; words: string }

export function NeedsDecisionProto({ fx, reviewer }: { fx: FixtureCase; reviewer: string }) {
  const readings = useMemo(() => readingsFor(fx), [fx])
  const [index, setIndex] = useState(0)
  const [viewed, setViewed] = useState<Record<string, Set<number>>>({})
  const [outcomes, setOutcomes] = useState<Record<string, Outcome>>({})
  const [notRight, setNotRight] = useState(false)
  const r = readings[index]
  const seen = viewed[r?.id ?? ""] ?? new Set<number>()
  const allSeen = r ? seen.size >= r.kinds.length : false
  const decided = Object.values(outcomes).filter((o) => o.kind !== "skipped").length

  const view = (i: number) => setViewed((v) => ({ ...v, [r.id]: new Set([...(v[r.id] ?? []), i]) }))
  const next = () => {
    setNotRight(false)
    setIndex((i) => Math.min(readings.length - 1, i + 1))
  }
  const confirm = () => {
    if (!allSeen) return
    setOutcomes((o) => ({ ...o, [r.id]: { kind: "confirmed", words: `Confirmed by ${reviewer}. Standard reason: Confirmed on the review screen after viewing ${r.kinds.length} examples across ${r.kinds.length} kinds.` } }))
    next()
  }
  const skip = () => {
    setOutcomes((o) => ({ ...o, [r.id]: { kind: "skipped", words: "Skipped" } }))
    next()
  }

  useEffect(
    () =>
      register("Needs a decision", [
        { key: "y", label: "Looks right", run: confirm },
        { key: "x", label: "Not right", run: () => setNotRight(true) },
        { key: "s", label: "Skip", run: skip },
        { key: "j", label: "Next reading", run: next },
        { key: "k", label: "Previous reading", run: () => setIndex((i) => Math.max(0, i - 1)) },
      ]),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [index, allSeen]
  )

  if (!r) return <p className="text-sm">Nothing needs a decision. New items appear when a phone is added or a reading changes.</p>
  return (
    <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
      <nav aria-label="Readings to check" className="rounded border bg-card p-2 text-sm">
        <p className="mb-1 font-medium" role="status">{decided} of {readings.length} checked</p>
        <ol className="flex flex-col gap-1">
          {readings.map((x, i) => (
            <li key={x.id}>
              <button type="button" aria-current={i === index ? "true" : undefined} onClick={() => setIndex(i)} className="w-full rounded px-1.5 py-1 text-left hover:bg-muted aria-[current=true]:bg-accent">
                {x.phone} · {x.app} ({fmt(x.affected.length)}){outcomes[x.id] ? ` · ${outcomes[x.id].kind === "confirmed" ? "looks right" : outcomes[x.id].kind === "not-right" ? "not right" : "skipped"}` : ""}
              </button>
            </li>
          ))}
        </ol>
      </nav>
      <section aria-labelledby="reading" className="flex flex-col gap-3">
        <h2 id="reading" className="text-base font-semibold">{r.sentence}</h2>
        <p className="text-sm">
          Examples drawn from all {fmt(r.affected.length)} messages, one of each kind present. <span role="status">{seen.size} of {r.kinds.length} kinds viewed</span>
        </p>
        <div className="grid gap-2 md:grid-cols-2">
          {r.kinds.map((k, i) => {
            const v = messageView(fx, k.example)
            return (
              <details key={k.kind} className="rounded border bg-card p-2 text-sm" onToggle={(e) => (e.currentTarget as HTMLDetailsElement).open && view(i)}>
                <summary className="cursor-pointer font-medium">{k.kind}{seen.has(i) ? " · viewed" : ""}</summary>
                <p className="mt-1">{v.time ? instantWords(v.time, v.zone) : "No time recorded"}</p>
                <p>{participantsLine(v)}</p>
                <p className="whitespace-pre-wrap rounded bg-background p-1">{k.example.body || <em>No text in this message</em>}</p>
                <p className="text-xs text-muted-foreground">Read as: sender {v.from?.name ?? "unknown"}</p>
              </details>
            )
          })}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={confirm} disabled={!allSeen} title={allSeen ? undefined : "Open every kind of example first"}>
            Looks right <kbd className="ml-1 text-xs">y</kbd>
          </Button>
          <Button variant="outline" onClick={() => setNotRight(true)}>
            Not right <kbd className="ml-1 text-xs">x</kbd>
          </Button>
          <Button variant="ghost" onClick={skip}>
            Skip <kbd className="ml-1 text-xs">s</kbd>
          </Button>
          {!allSeen && <span className="text-sm text-muted-foreground">Looks right is available once every kind of example has been opened.</span>}
        </div>
        {notRight && (
          <fieldset className="rounded border p-2 text-sm">
            <legend className="font-medium">What is wrong?</legend>
            {["The sender is the other party", "This is when it was read, not sent"].map((c) => (
              <Button
                key={c}
                size="sm"
                variant="outline"
                className="mr-2 mt-1"
                onClick={() => {
                  setOutcomes((o) => ({ ...o, [r.id]: { kind: "not-right", words: `Corrected by ${reviewer}: ${c}. Applies to ${r.phone} in this case.` } }))
                  next()
                }}
              >
                {c}
              </Button>
            ))}
          </fieldset>
        )}
        {outcomes[r.id] && <p role="status" className="text-sm">{outcomes[r.id].words}</p>}
      </section>
    </div>
  )
}
