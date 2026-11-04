import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { caseMembersAPI } from "@/features/cases/members-api"
import { shareFailure } from "../review-share"
import { fmt } from "../ui/count-sentence"
import { ExampleView } from "./ExampleView"
import { readingsAPI, type RecheckItem, type RecheckSummary } from "./readings.api"

/**
 * A second person re-checks a 5% sample of the confirmations, and the disagreement rate is reported (07 J-8). The rate
 * is the server's sentence: true counts always, a percentage only on a base large enough for one. A person never
 * draws or checks their own confirmations; the first confirmation is kept as it is.
 */
export function ReadingRechecks({ caseId }: { caseId: string }) {
  const q = useQuery({ queryKey: ["phone-reading-rechecks", caseId], queryFn: () => readingsAPI.rechecks(caseId) })
  if (q.isLoading) return null
  if (q.isError) return <p role="alert" className="text-sm">{shareFailure(q.error, "The re-checks could not be loaded.")}</p>
  const s = q.data!
  const mine = s.items.filter((i) => i.mine && !i.result)
  const disagreed = s.items.filter((i) => i.result && !i.result.agrees)
  return (
    <section aria-labelledby="rechecks" className="flex flex-col gap-2 rounded border bg-card p-3 text-sm">
      <h2 id="rechecks" className="text-base font-semibold">Re-check of confirmations</h2>
      <p role="status">{s.words}</p>
      {s.passes.map((p) => (
        <p key={p.pass_id} className="text-xs text-muted-foreground">
          {fmt(p.sampled)} of {fmt(p.eligible)} sampled for {p.reviewer ?? "a person"} ({p.percent}%, seed {p.seed}).
        </p>
      ))}
      {disagreed.length > 0 && (
        <ul aria-label="Disagreements" className="flex flex-col gap-1">
          {disagreed.map((i) => (
            <li key={i.confirmation_id}>
              {i.sentence} {i.result!.by_name} disagrees with {i.first.by_name ?? "the confirmation"}: {i.result!.note}
            </li>
          ))}
        </ul>
      )}
      {mine.length > 0 && (
        <ol aria-label="Readings for you to re-check" className="flex flex-col gap-2">
          {mine.map((i) => <RecheckRow key={i.confirmation_id} caseId={caseId} item={i} />)}
        </ol>
      )}
      <Draw caseId={caseId} summary={s} />
    </section>
  )
}

function RecheckRow({ caseId, item }: { caseId: string; item: RecheckItem }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState("")
  const [error, setError] = useState<string | null>(null)
  const ex = useQuery({
    queryKey: ["phone-reading-examples", caseId, item.reading_id],
    queryFn: () => readingsAPI.examples(caseId, item.reading_id!),
    enabled: open && !!item.reading_id,
  })
  const save = useMutation({
    mutationFn: (agrees: boolean) => readingsAPI.recordRecheck(caseId, item.task_id, item.confirmation_id, agrees, note),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["phone-reading-rechecks", caseId] }),
    onError: (e) => setError(shareFailure(e, "The re-check could not be saved.")),
  })
  return (
    <li data-testid="recheck-row" className="flex flex-col gap-1 rounded border p-2">
      <p>{item.sentence}</p>
      <p className="text-xs text-muted-foreground">Confirmed by {item.first.by_name ?? "a person"}. {item.first.reason}{item.status_now === "corrected" ? " It has been corrected since." : ""}</p>
      {!item.reading_id && <p>This reading is no longer on the phone's current report, so there are no examples to look at.</p>}
      {item.reading_id && <div><Button size="sm" variant="outline" aria-expanded={open} onClick={() => setOpen((o) => !o)}>Examples</Button></div>}
      {open && ex.data?.kinds.map((k) => <ExampleView key={k.id} k={k} />)}
      {open && ex.isError && <p role="alert">The examples could not be loaded.</p>}
      {item.own_confirmation ? (
        <p>You confirmed this one, so someone else needs to re-check it.</p>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <input aria-label="Re-check note" className="h-7 min-w-48 rounded border px-2" placeholder="Note (needed to disagree)" value={note} onChange={(e) => setNote(e.target.value)} maxLength={4000} />
          <Button size="sm" variant="outline" disabled={save.isPending} onClick={() => save.mutate(true)}>Agrees</Button>
          <Button size="sm" variant="outline" disabled={save.isPending || !note.trim()} onClick={() => save.mutate(false)} title={!note.trim() ? "Say why you disagree" : undefined}>Disagrees</Button>
        </div>
      )}
      {error && <p role="alert">{error}</p>}
    </li>
  )
}

function Draw({ caseId, summary }: { caseId: string; summary: RecheckSummary }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [who, setWho] = useState("")
  const [words, setWords] = useState<string | null>(null)
  const membersQ = useQuery({ queryKey: ["case-members", caseId], queryFn: () => caseMembersAPI.list(caseId), enabled: open })
  const members = (membersQ.data ?? []).filter((m) => m.preset !== "viewer")
  const draw = useMutation({
    mutationFn: () => readingsAPI.drawRecheck(caseId, who),
    onSuccess: (m) => {
      setWords(m.words)
      setOpen(false)
      void qc.invalidateQueries({ queryKey: ["phone-reading-rechecks", caseId] })
    },
    onError: (e) => setWords(shareFailure(e, "The sample could not be drawn.")),
  })
  return (
    <div className="flex flex-col gap-1">
      {open ? (
        <div className="flex flex-wrap items-center gap-2">
          <label>
            Second person{" "}
            <select aria-label="Second person" className="h-7 rounded border bg-background px-1" value={who} onChange={(e) => setWho(e.target.value)}>
              <option value="">Choose a person</option>
              {members.map((m) => <option key={m.user_id} value={m.user_id}>{m.user_name || m.user_email}</option>)}
            </select>
          </label>
          <Button size="sm" disabled={!who || draw.isPending} onClick={() => draw.mutate()}>Draw the sample</Button>
          <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
        </div>
      ) : (
        <div><Button size="sm" variant="outline" onClick={() => { setOpen(true); setWords(null) }}>Draw a {summary.percent}% re-check…</Button></div>
      )}
      <p className="text-xs text-muted-foreground">A random {summary.percent}% of the confirmations, each made by someone else, go to the second person. The seed is kept, and the confirmations are never changed.</p>
      {words && <p role="status">{words}</p>}
    </div>
  )
}
