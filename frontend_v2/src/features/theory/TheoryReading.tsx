import { useMemo, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { NarrativeBlock } from "./NarrativeBlock"
import { memberHref, opensAsGroup, useOpenGroup } from "./source-links"
import { SURFACE_WORDS, theoryAPI, theoryMembersAPI, type Addition, type LoupeView, type Member, type Surface } from "./api"

/**
 * A theory read as a whole (lx-theorybuild C, G, H): its additions in the order added, grouped by where they came
 * from, each with why it was chosen, who added it (a model's choice says so), its own narrative, "View through the
 * Loupe" (the addition alone in the view that suits it, its narrative beside it) and a way back to its source. Above
 * them, the theory's own "how it fits together", and the theory as its own timeline, graph and map.
 */
const KIND_ORDER: Surface[] = ["graph", "significant", "timeline", "financial", "evidence", "passage", "interview", "phone", "map", "agent", "search", "workspace"]

function kindOf(a: Addition): Surface {
  if (a.surface) return a.surface
  if (a.target_type.startsWith("phone_")) return "phone"
  if (a.target_type.startsWith("financial_")) return "financial"
  if (a.target_type === "evidence_passage") return "passage"
  if (a.target_type === "evidence") return "evidence"
  if (a.target_type === "graph_entity") return "graph"
  if (a.target_type === "agent_answer" || a.target_type === "agent_artifact") return "agent"
  if (a.target_type === "timeline_event") return "timeline"
  if (a.target_type === "witness") return "interview"
  return "workspace"
}

function addedWords(a: Addition): string {
  const when = a.added_at ? new Date(a.added_at).toLocaleString() : ""
  if (a.origin === "agent") return `Chosen by ${a.model || "the case model"} (a model's choice)${a.accepted_by ? `, accepted by ${a.accepted_by}` : ""}${when ? ` · ${when}` : ""}`
  return `Added by ${a.added_by || "someone"}${when ? ` · ${when}` : ""}`
}

export function TheoryReadingSection({ caseId, entryId }: { caseId: string; entryId: string }) {
  const reading = useQuery({ queryKey: ["theory-reading", caseId, entryId], queryFn: () => theoryAPI.reading(caseId, entryId), enabled: !!entryId })
  const [lens, setLens] = useState<Addition | null>(null)
  const [whole, setWhole] = useState<"timeline" | "graph" | "map" | null>(null)
  const groups = useMemo(() => {
    const out = new Map<Surface, Addition[]>()
    for (const a of reading.data?.additions ?? []) {
      const k = kindOf(a)
      out.set(k, [...(out.get(k) ?? []), a])
    }
    return KIND_ORDER.filter((k) => out.has(k)).map((k) => [k, out.get(k)!] as const)
  }, [reading.data])
  if (reading.isLoading) return <p className="text-sm text-muted-foreground">Reading the theory…</p>
  if (reading.error) return <p role="alert" className="text-sm text-status-error">{reading.error instanceof Error ? reading.error.message : "The theory could not be read"}</p>
  const data = reading.data
  if (!data) return null
  const isTheory = data.entry.entry_type === "theory"
  return (
    <section aria-label="The theory, read as a whole" className="flex flex-col gap-3">
      {isTheory && (
        <div className="flex flex-col gap-1">
          <h3 className="text-sm font-semibold">How it fits together</h3>
          <NarrativeBlock
            caseId={caseId}
            entryId={entryId}
            linkId={null}
            narrative={data.fit}
            versions={data.fit_versions}
            emptyWords={data.additions.length ? "No account of how these fit together yet." : "Add items to the theory first."}
          />
          <div className="flex flex-wrap gap-1" role="group" aria-label="View the theory as">
            {(["timeline", "graph", "map"] as const).map((v) => (
              <Button key={v} size="sm" variant={whole === v ? "secondary" : "outline"} aria-pressed={whole === v} onClick={() => setWhole(whole === v ? null : v)} disabled={!data.additions.length}>
                As a {v}
              </Button>
            ))}
          </div>
          {whole && <TheoryWhole caseId={caseId} entryId={entryId} view={whole} />}
        </div>
      )}
      <h3 className="text-sm font-semibold">
        {data.additions.length.toLocaleString("en-US")} {data.additions.length === 1 ? "addition" : "additions"}
      </h3>
      {groups.map(([kind, items]) => (
        <div key={kind} className="flex flex-col gap-2">
          <h4 className="text-xs uppercase tracking-wide text-muted-foreground">From {SURFACE_WORDS[kind]}</h4>
          {items.map((a) => (
            <article key={a.link_id} className="flex flex-col gap-1 rounded border p-2" aria-label={a.label}>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-sm font-medium">{a.label}</p>
                <div className="flex gap-1">
                  <Button size="sm" variant="outline" onClick={() => setLens(a)}>
                    View through the Loupe
                  </Button>
                  <OpenSource caseId={caseId} entryId={entryId} a={a} />
                </div>
              </div>
              {a.why && <p className="text-sm">Why: {a.why}</p>}
              {!!a.left_out && <p className="text-xs">{a.left_out.toLocaleString("en-US")} chosen items were not in this case and were not kept.</p>}
              <p className={`text-xs ${a.origin === "agent" ? "text-status-review" : "text-muted-foreground"}`}>
                {addedWords(a)}
                {a.model_reading && ` · an answer from ${a.model || "the case agent"}: a model reading`}
                {a.relationship !== "unclassified" && ` · ${a.relationship}`}
              </p>
              <NarrativeBlock
                caseId={caseId}
                entryId={entryId}
                linkId={a.link_id}
                narrative={a.narrative}
                versions={a.narrative_versions}
                emptyWords="No narrative yet: what does this show?"
              />
            </article>
          ))}
        </div>
      ))}
      {lens && <LoupeDialog caseId={caseId} entryId={entryId} addition={lens} onClose={() => setLens(null)} />}
    </section>
  )
}

function OpenSource({ caseId, entryId, a }: { caseId: string; entryId: string; a: Addition }) {
  const qc = useQueryClient()
  const open = useOpenGroup(caseId)
  const [error, setError] = useState<string | null>(null)
  const href = a.kind === "single" && a.target_type !== "graph_entity" ? memberHref(caseId, a.target_type, a.target_id, a.source_anchor) : null
  if (href) return <a className="self-center text-xs underline underline-offset-2" href={href}>Open where it came from</a>
  if (!opensAsGroup(a.target_type)) return null
  const go = async () => {
    setError(null)
    try {
      const view = await qc.fetchQuery({ queryKey: ["theory-loupe", caseId, entryId, a.link_id], queryFn: () => theoryAPI.loupe(caseId, entryId, a.link_id) })
      open({ label: a.label, linkId: a.link_id, targetType: a.target_type, how: view.group?.how ?? a.how, members: view.members })
    } catch (e) {
      setError(e instanceof Error ? e.message : "It could not be opened")
    }
  }
  return (
    <span className="inline-flex items-center gap-1">
      <button type="button" className="self-center text-xs underline underline-offset-2" onClick={() => void go()}>
        Open where it came from
      </button>
      {error && <span role="alert" className="text-xs text-status-error">{error}</span>}
    </span>
  )
}

function money(m: Member): string {
  if (m.amount_minor === undefined || !m.currency) return ""
  const v = (m.amount_minor / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${v} ${m.currency} ${m.direction === "credit" ? "in" : "out"}`
}

function stateWords(m: Member): string | null {
  if (m.state === "deleted") return "deleted, in Deleted items"
  if (m.state === "corrected") return "corrected: the correction is what counts"
  if (m.state === "rejected") return "rejected from the ledger"
  if (m.state === "gone") return "no longer in the case"
  return null
}

/** The members in the view that suits them: ledger rows as a ledger, dated items as a timeline, the rest as a list. */
export function MembersView({ caseId, members }: { caseId: string; members: Member[] }) {
  const rows = members.filter((m) => m.type === "financial_transaction")
  const dated = members.filter((m) => m.date && m.type !== "financial_transaction").sort((a, b) => (a.date! < b.date! ? -1 : 1))
  const rest = members.filter((m) => m.type !== "financial_transaction" && !m.date)
  // Only rows as they stand count in a sum: a corrected, rejected or deleted row is shown, not added up (rule 1).
  const counted = rows.filter((m) => m.state === "present")
  const currencies = [...new Set(counted.map((m) => m.currency))]
  const sum = (dir: string) => counted.filter((m) => m.direction === dir).reduce((s, m) => s + (m.amount_minor ?? 0), 0)
  return (
    <div className="flex flex-col gap-3 text-sm">
      {rows.length > 0 && (
        <div>
          <p className="font-medium">Ledger rows ({rows.length.toLocaleString("en-US")})</p>
          {currencies.length === 1 && (
            <p className="text-xs text-muted-foreground">
              In {(sum("credit") / 100).toLocaleString("en-US", { minimumFractionDigits: 2 })} {currencies[0]} · out{" "}
              {(sum("debit") / 100).toLocaleString("en-US", { minimumFractionDigits: 2 })} {currencies[0]}
              {counted.length < rows.length && ` · ${rows.length - counted.length} corrected, rejected or missing row(s) not counted`}
            </p>
          )}
          <table className="w-full text-xs">
            <tbody>
              {[...rows].sort((a, b) => ((a.date ?? "") < (b.date ?? "") ? -1 : 1)).map((m) => (
                <tr key={m.ref} className={m.state !== "present" ? "opacity-60" : ""}>
                  <td className="pr-2 align-top">{m.date ?? "undated"}</td>
                  <td className="pr-2 align-top whitespace-nowrap">{money(m)}</td>
                  <td className="align-top">
                    <MemberLink caseId={caseId} m={m} words={m.text.split(" · ").slice(2).join(" · ") || m.label} />
                    {stateWords(m) && <span className="ml-1 text-status-review">({stateWords(m)})</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {dated.length > 0 && (
        <div>
          <p className="font-medium">On the timeline ({dated.length.toLocaleString("en-US")})</p>
          <ol className="flex flex-col gap-0.5">
            {dated.map((m) => (
              <li key={m.ref}>
                <span className="mr-2 text-xs text-muted-foreground">{m.date}</span>
                <MemberLink caseId={caseId} m={m} words={m.label} />
                {stateWords(m) && <span className="ml-1 text-xs text-status-review">({stateWords(m)})</span>}
              </li>
            ))}
          </ol>
        </div>
      )}
      {rest.length > 0 && (
        <ul className="flex flex-col gap-1">
          {rest.map((m) => (
            <li key={m.ref}>
              <MemberLink caseId={caseId} m={m} words={m.label} />
              {m.text && m.text !== m.label && !m.text.endsWith(`: ${m.label}`) && <p className="whitespace-pre-wrap text-xs text-muted-foreground">{m.text}</p>}
              {stateWords(m) && <span className="ml-1 text-xs text-status-review">({stateWords(m)})</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function MemberLink({ caseId, m, words }: { caseId: string; m: Member; words: string }) {
  const href = memberHref(caseId, m.type, m.id, {})
  return href ? <a className="underline underline-offset-2" href={href}>{words}</a> : <span>{words}</span>
}

export function LoupeDialog({ caseId, entryId, addition, onClose }: { caseId: string; entryId: string; addition: Addition; onClose: () => void }) {
  const open = useOpenGroup(caseId)
  const view = useQuery({ queryKey: ["theory-loupe", caseId, entryId, addition.link_id], queryFn: () => theoryAPI.loupe(caseId, entryId, addition.link_id) })
  const data: LoupeView | undefined = view.data
  const a = data?.addition ?? addition
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-auto">
        <DialogHeader>
          <DialogTitle>Through the Loupe: {a.label}</DialogTitle>
          <DialogDescription>
            {a.why ? `Chosen: ${a.why}. ` : ""}
            {addedWords(a)}
          </DialogDescription>
        </DialogHeader>
        {view.isLoading && <p className="text-sm">Opening…</p>}
        {view.error && <p role="alert" className="text-sm text-status-error">{view.error instanceof Error ? view.error.message : "It could not be opened"}</p>}
        {data && (
          <div className="grid gap-4 md:grid-cols-[3fr_2fr]">
            <div className="flex flex-col gap-2">
              {data.group && (
                <p className="text-xs text-muted-foreground">
                  {data.group.label}
                  {Object.keys(data.group.how || {}).length > 0 && ` · how: ${describeHow(data.group.how)}`}
                  {data.group.left_out > 0 && ` · ${data.group.left_out} not in this case, not kept`}
                </p>
              )}
              {data.missing && <p role="alert" className="text-sm">{data.missing}</p>}
              {opensAsGroup(a.target_type) && data.members.length > 0 && (
                <div>
                  <Button size="sm" variant="outline" onClick={() => open({ label: a.label, linkId: a.link_id, targetType: a.target_type, how: data.group?.how ?? a.how, members: data.members })}>
                    Open these where they came from
                  </Button>
                </div>
              )}
              {data.members_shown < data.member_count && (
                <p className="text-xs">Showing {data.members_shown.toLocaleString("en-US")} of {data.member_count.toLocaleString("en-US")} items.</p>
              )}
              <MembersView caseId={caseId} members={data.members} />
            </div>
            <div className="flex flex-col gap-1">
              <h3 className="text-sm font-semibold">What it shows</h3>
              <NarrativeBlock
                caseId={caseId}
                entryId={entryId}
                linkId={a.link_id}
                narrative={a.narrative}
                versions={a.narrative_versions}
                history={data.history}
                emptyWords="No narrative yet: write one, or ask the model for a reading."
              />
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

export function describeHow(how: Record<string, unknown>): string {
  const parts: string[] = []
  for (const [k, v] of Object.entries(how)) {
    if (v === null || v === undefined || v === "") continue
    if (typeof v === "object") {
      const inner = Object.entries(v as Record<string, unknown>).filter(([, x]) => x !== null && x !== undefined && x !== "" && !(Array.isArray(x) && !x.length))
      if (inner.length) parts.push(`${k} ${inner.map(([ik, iv]) => `${ik} ${Array.isArray(iv) ? iv.join(", ") : String(iv)}`).join("; ")}`)
    } else parts.push(`${k} ${String(v)}`)
  }
  return parts.join(" · ") || "chosen by hand"
}

function TheoryWhole({ caseId, entryId, view }: { caseId: string; entryId: string; view: "timeline" | "graph" | "map" }) {
  const open = useOpenGroup(caseId)
  const q = useQuery({ queryKey: ["theory-members", caseId, entryId], queryFn: () => theoryMembersAPI.get(caseId, entryId) })
  if (q.isLoading) return <p className="text-sm">Gathering what the theory holds…</p>
  if (q.error || !q.data) return <p role="alert" className="text-sm text-status-error">{q.error instanceof Error ? q.error.message : "Not available"}</p>
  const d = q.data
  const cut = d.members_shown < d.member_count ? ` Showing ${d.members_shown.toLocaleString("en-US")} of ${d.member_count.toLocaleString("en-US")}.` : ""
  if (view === "timeline") {
    const dated = d.members.filter((m) => m.date)
    return (
      <div className="rounded border p-2">
        <p className="text-xs text-muted-foreground">
          {dated.length.toLocaleString("en-US")} dated of {d.members_shown.toLocaleString("en-US")} items the theory holds.{cut}
        </p>
        <MembersView caseId={caseId} members={dated} />
      </div>
    )
  }
  const keys = d.graph_keys
  return (
    <div className="rounded border p-2 text-sm">
      <p>
        {keys.length.toLocaleString("en-US")} graph {keys.length === 1 ? "entity" : "entities"} in this theory.{cut}{" "}
        {keys.length > 0 && (
          <button
            type="button"
            className="underline underline-offset-2"
            onClick={() => open({ label: d.entry.title || "This theory", linkId: entryId, targetType: view === "map" ? "map_selection" : "graph_selection", members: keys.map((id) => ({ type: "graph_entity", id })) })}
          >
            Open them on the {view}
          </button>
        )}
      </p>
    </div>
  )
}
