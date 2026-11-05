import { useState } from "react"
import { Link } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { citationHref } from "@/features/financial/lib/judgements"
import { agentProposalKeys, fetchGlossary, withdrawGlossaryTerm, type GlossaryMention, type GlossaryTerm } from "../agent-proposals"

function Mention({ caseId, mention }: { caseId: string; mention: GlossaryMention }) {
  const href = citationHref(caseId, mention.rec)
  return (
    <li className="space-y-0.5" data-testid="glossary-mention">
      <p>
        {href ? <a className="underline" href={href} target="_blank" rel="noreferrer">{mention.at ? mention.at.slice(0, 16).replace("T", " ") : "No time"}</a> : mention.at}
        {mention.people.length ? ` · ${mention.people.join(", ")}` : ""}
      </p>
      {mention.rows.length > 0 && (
        <ul className="list-disc pl-4">
          {mention.rows.map((row) => (
            <li key={row.payment} data-testid="glossary-row">
              <Link className="underline" to={`/cases/${caseId}/financial?view=transactions&payment=${row.payment}`}>Payment {row.ref ?? ""}</Link>{" "}
              {row.amount} on {row.date}, {row.paid_by} to {row.paid_to} ({row.days_from_mention === 0 ? "same day" : `${Math.abs(row.days_from_mention)} days ${row.days_from_mention > 0 ? "after" : "before"}`})
            </li>
          ))}
        </ul>
      )}
      {mention.join_reason && <p className="text-muted-foreground">{mention.join_reason}</p>}
      {mention.rows_outside_window > 0 && (
        <p className="text-muted-foreground">{mention.rows_outside_window.toLocaleString("en-US")} other rows between them fall outside the window.</p>
      )}
    </li>
  )
}

function Term({ caseId, term, canEdit }: { caseId: string; term: GlossaryTerm; canEdit: boolean }) {
  const client = useQueryClient()
  const [why, setWhy] = useState("")
  const [err, setErr] = useState<string | null>(null)
  const m = term.mentions
  const withdraw = () =>
    withdrawGlossaryTerm(caseId, term.id, why)
      .then(() => client.invalidateQueries({ queryKey: agentProposalKeys.glossary(caseId) }))
      .catch((e: Error) => setErr(e.message))
  return (
    <li className="space-y-1 rounded border p-2 text-sm" data-testid="glossary-term" data-status={term.status}>
      <p className="font-semibold">“{term.term}”: {term.meaning}</p>
      <p className="text-xs" data-testid="glossary-reading">{term.reading_words}</p>
      {term.meaning_changed && term.model_meaning && <p className="text-xs text-muted-foreground">The model read it as: {term.model_meaning}</p>}
      {term.speaker && <p className="text-xs">Used by: {term.speaker}</p>}
      {term.status === "withdrawn" && <p className="text-xs">Withdrawn by {term.withdrawn_by}: {term.withdrawn_reason}</p>}
      {term.keyword_list_note && <p role="status" className="text-xs">{term.keyword_list_note}</p>}
      {m && (
        <details>
          <summary className="cursor-pointer text-xs" data-testid="glossary-count">
            {m.total.toLocaleString("en-US")} {m.total === 1 ? "mention" : "mentions"}, {m.with_rows.toLocaleString("en-US")} joined to ledger rows
          </summary>
          <p className="mt-1 text-xs text-muted-foreground">{m.join_rule}</p>
          <ul className="mt-1 space-y-1 text-xs">{m.items.map((x) => <Mention key={x.rec} caseId={caseId} mention={x} />)}</ul>
          {m.search_limits.map((x) => <p key={x} role="status" className="text-xs">{x}</p>)}
        </details>
      )}
      {term.status === "confirmed" && canEdit && (
        <div className="flex flex-wrap items-center gap-2">
          <Input aria-label={`Why withdraw ${term.term}`} className="h-8 w-64" placeholder="Why it is withdrawn" value={why} onChange={(e) => setWhy(e.target.value)} />
          <Button size="sm" variant="outline" disabled={!why.trim()} onClick={withdraw}>Withdraw</Button>
        </div>
      )}
      {err && <p role="alert" className="text-xs text-destructive">{err}</p>}
    </li>
  )
}

/** Code words people confirmed: each stays labelled as that person's reading, with every mention and its ledger rows. */
export function GlossaryPanel({ caseId, canEdit }: { caseId: string; canEdit: boolean }) {
  const q = useQuery({ queryKey: agentProposalKeys.glossary(caseId), queryFn: () => fetchGlossary(caseId) })
  return (
    <section className="space-y-2 pt-2" aria-label="Code words">
      <h2 className="text-base font-semibold">Code words</h2>
      {q.isPending ? (
        <p role="status">Loading code words…</p>
      ) : q.isError ? (
        <p role="alert">{q.error.message}</p>
      ) : !q.data.items.length ? (
        <p className="text-sm text-muted-foreground">No code word has been confirmed by a person in this case.</p>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">{q.data.limitation}</p>
          <ul className="space-y-2">{q.data.items.map((t) => <Term key={t.id} caseId={caseId} term={t} canEdit={canEdit} />)}</ul>
        </>
      )}
    </section>
  )
}
