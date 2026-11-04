import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { caseMembersAPI } from "@/features/cases/members-api"
import { getReviewCoverage, shareFailure, startSecondPass, type CoverageThread } from "../review-share"

const n = (v: number) => v.toLocaleString("en-US")

/**
 * The phone's review coverage summary (07 J-13 step 6): not yet reviewed, reviewed and partly reviewed (a thread
 * whose messages grew after its review says by whom, when, how many it had then and how many were added since,
 * J-13b), who reviewed what, the review tasks, the second-pass results, the searches run and the terms used. The
 * same summary prints on the export cover. Every list is whole.
 */
export function ReviewCoverage({ caseId, extraction }: { caseId: string; extraction: string }) {
  const q = useQuery({
    queryKey: ["phone-review-coverage", caseId, extraction],
    queryFn: () => getReviewCoverage(caseId, [extraction]),
    enabled: !!caseId && !!extraction,
  })
  if (q.isLoading) return <p role="status">Counting reviewed threads.</p>
  if (q.isError || !q.data) return <p role="alert">The review coverage could not be loaded.</p>
  const c = q.data
  const link = (t: CoverageThread) => (
    <Link className="underline" to={`/cases/${encodeURIComponent(caseId)}/conversations?thread=${encodeURIComponent(t.thread_key)}`}>{t.title}</Link>
  )
  return (
    <div className="flex flex-col gap-2" data-testid="review-coverage">
      <p>Not yet reviewed: {n(c.counts.not_reviewed)} of {n(c.counts.threads)} threads</p>
      <p>
        Reviewed: {n(c.counts.reviewed)}. Partly reviewed: {n(c.counts.partly_reviewed)}.
      </p>
      {c.partly_reviewed.length > 0 && (
        <ul aria-label="Partly reviewed threads" className="list-disc pl-4">
          {c.partly_reviewed.map((t) => <li key={t.thread_key}>{link(t)}: {t.review}</li>)}
        </ul>
      )}
      {c.reviewers.length > 0 && (
        <p data-testid="reviewed-by">
          Reviewed by: {c.reviewers.map((p) => `${p.name}, ${n(p.reviewed)} ${p.reviewed === 1 ? "thread" : "threads"}${p.partly_reviewed ? ` and ${n(p.partly_reviewed)} partly` : ""}`).join("; ")}.
        </p>
      )}
      {c.not_reviewed.length > 0 && (
        <details>
          <summary>Threads not yet reviewed ({n(c.not_reviewed.length)})</summary>
          <ul className="list-disc pl-4">
            {c.not_reviewed.map((t) => <li key={t.thread_key}>{link(t)} on {t.phone}, {n(t.messages)} {t.messages === 1 ? "message" : "messages"}</li>)}
          </ul>
        </details>
      )}
      {c.splits.length > 0 && (
        <div>
          <p className="font-medium">Review tasks in this case (every phone)</p>
          <ul className="list-disc pl-4" data-testid="review-tasks">
            {c.splits.map((s) => <li key={s.task_id}>{s.words}</li>)}
          </ul>
        </div>
      )}
      <SecondPass caseId={caseId} summary={c} />
      <div data-testid="searches-run">
        <p className="font-medium">Searches run</p>
        {c.searches.length === 0 ? (
          <p>No search of the case's phone records is recorded.</p>
        ) : (
          <ul className="list-disc pl-4">
            {c.searches.map((s) => (
              <li key={`${s.query}|${s.exact}`}>
                "{s.query}"{s.exact ? " (exact characters)" : ""}: run {n(s.runs)} {s.runs === 1 ? "time" : "times"} by {s.people.join(", ")}
                {s.last_hits != null ? `; ${n(s.last_hits)} found the last time` : ""}
              </li>
            ))}
          </ul>
        )}
        {c.keyword_lists.map((k) => <p key={k.name}>Keyword list "{k.name}": {k.terms.map((t) => `"${t}"`).join("; ")}.</p>)}
        {c.terms.length > 0 && <p>Terms used: {c.terms.map((t) => `"${t}"`).join(", ")}.</p>}
      </div>
    </div>
  )
}

function SecondPass({ caseId, summary }: { caseId: string; summary: Awaited<ReturnType<typeof getReviewCoverage>> }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [who, setWho] = useState("")
  const [note, setNote] = useState<string | null>(null)
  const membersQ = useQuery({ queryKey: ["case-members", caseId], queryFn: () => caseMembersAPI.list(caseId), enabled: open })
  const draw = useMutation({
    mutationFn: () => startSecondPass(caseId, who),
    onSuccess: (r) => {
      setNote(`${r.words} The task "${r.title}" is in Workspace.`)
      setOpen(false)
      void qc.invalidateQueries({ queryKey: ["phone-review-coverage"] })
    },
    onError: (e) => setNote(shareFailure(e, "The second-pass sample could not be drawn.")),
  })
  return (
    <div data-testid="second-pass-summary">
      <p className="font-medium">Second pass</p>
      {summary.second_pass.length === 0 && <p>No second-pass sample has been drawn.</p>}
      <ul className="list-disc pl-4">
        {summary.second_pass.map((s) => (
          <li key={s.pass_id}>
            {s.percent}% sample (seed {s.seed}) for {s.reviewer ?? "a person"}: {n(s.sampled)} sampled, {n(s.agrees)} agree, {n(s.disagrees)} disagree, {n(s.pending)} not yet checked.
            {s.disagreements.map((d) => (
              <span key={d.thread_key} className="block">{d.by} disagrees with {d.first_by ?? "the first"}'s review of "{d.title}": {d.note}</span>
            ))}
          </li>
        ))}
      </ul>
      {open ? (
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-sm">
            Second reviewer{" "}
            <select className="rounded border px-1" value={who} onChange={(e) => setWho(e.target.value)}>
              <option value="">Choose a person</option>
              {(membersQ.data ?? []).filter((m) => m.preset !== "viewer").map((m) => <option key={m.user_id} value={m.user_id}>{m.user_name}</option>)}
            </select>
          </label>
          <Button size="sm" disabled={!who || draw.isPending} onClick={() => draw.mutate()}>Draw a 10% sample</Button>
          <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
        </div>
      ) : (
        <Button size="sm" variant="outline" onClick={() => { setOpen(true); setNote(null) }}>Second pass…</Button>
      )}
      <p className="text-xs">A random 10% of the case's fully reviewed threads, each first reviewed by someone else, go to the second reviewer. The seed is kept, and the first review is never changed.</p>
      {note && <p role="status">{note}</p>}
    </div>
  )
}
