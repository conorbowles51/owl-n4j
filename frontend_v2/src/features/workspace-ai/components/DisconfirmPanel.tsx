import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  agentProposalKeys,
  fetchDisconfirm,
  planDisconfirm,
  startDisconfirm,
  stopDisconfirm,
  type DisconfirmState,
  type DisconfirmSweep,
} from "../agent-proposals"

function plural(n: number, word: string) {
  return `${n.toLocaleString("en-US")} ${word}${n === 1 ? "" : "s"}`
}

function duration(seconds: number) {
  if (seconds < 60) return `${seconds} s`
  return `${Math.floor(seconds / 60)} min ${seconds % 60} s`
}

function isActive(sweep: DisconfirmSweep | null | undefined) {
  return sweep?.job_status === "queued" || sweep?.job_status === "running"
}

/** The page-speed standard's panel: the step in words, completion from true counts, time left as an estimate. */
function Progress({ sweep }: { sweep: DisconfirmSweep }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  const started = sweep.started_at ? Date.parse(sweep.started_at) : null
  const elapsed = started ? Math.max(0, Math.round((now - started) / 1000)) : 0
  const reads = sweep.reads
  const reading = sweep.stage === "reading"
  return (
    <div role="status" className="space-y-1 rounded border p-2" data-testid="disconfirm-progress">
      <p className="font-medium">{sweep.step}</p>
      <div
        className="h-1.5 w-full overflow-hidden rounded bg-muted"
        role="progressbar"
        aria-valuenow={sweep.progress}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="h-full bg-primary" style={{ width: `${sweep.progress}%` }} />
      </div>
      <p className="text-xs text-muted-foreground">
        {reading ? `${reads.done} of ${reads.total} reads done, ${reads.running} running. ` : ""}
        {started ? `Running for ${duration(elapsed)}. ` : ""}
        {sweep.time_left ? `About ${duration(sweep.time_left.seconds)} left (${sweep.time_left.label}).` : ""}
      </p>
      {reads.slow && (
        <p className="text-xs" data-testid="disconfirm-slow">
          One read has been running for {duration(reads.slowest_running_seconds ?? 0)}, longer than usual. It is still
          running.
        </p>
      )}
      {sweep.cancel_requested && <p className="text-xs">Stopping: reads already out are being finished.</p>}
    </div>
  )
}

function Plan({
  sweep,
  busy,
  onStart,
}: {
  sweep: DisconfirmSweep
  busy: boolean
  onStart: (limit?: number) => void
}) {
  const [limit, setLimit] = useState("")
  const left = sweep.reads.pending + sweep.reads.failed
  const clipped = Number(limit)
  const valid = Number.isInteger(clipped) && clipped >= 1 && clipped < left
  return (
    <div className="space-y-2 rounded border p-2" data-testid="disconfirm-plan">
      <p>
        {left === sweep.reads.total
          ? `The searches matched ${plural(sweep.reads.items, "item")}. Reading them takes ${plural(left, "model call")} on ${sweep.model.model_id}. No model call has been spent on them yet.`
          : `${plural(left, "read")} of ${sweep.reads.total} ${left === 1 ? "is" : "are"} left.`}
      </p>
      {sweep.reads.seconds_per_read != null && (
        <p className="text-xs text-muted-foreground">
          {sweep.reads.seconds_per_read} s per read so far; {sweep.cost.calls} model calls, $
          {sweep.cost.usd.toFixed(4)} spent.
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" disabled={busy} onClick={() => onStart()}>
          {left === sweep.reads.total ? `Run all ${plural(left, "read")}` : `Run the ${plural(left, "remaining read")}`}
        </Button>
        {left > 1 && (
          <>
            <Input
              className="h-8 w-20"
              inputMode="numeric"
              aria-label="Run only this many reads"
              placeholder="First…"
              value={limit}
              onChange={(event) => setLimit(event.target.value)}
            />
            <Button size="sm" variant="ghost" disabled={busy || !valid} onClick={() => onStart(clipped)}>
              Run only these
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

function Result({ sweep }: { sweep: DisconfirmSweep }) {
  const absences = sweep.absences?.items ?? []
  const named = absences.filter((a) => a.expectation)
  const seen = absences.filter((a) => !a.expectation)
  return (
    <div className="space-y-3" data-testid="disconfirm-result">
      <p className="font-medium">{sweep.outcome.headline}</p>
      <p className="text-xs text-muted-foreground">
        {sweep.model.words} {sweep.outcome.not_support} Cost of this sweep: ${sweep.cost.usd.toFixed(4)},{" "}
        {plural(sweep.cost.calls, "model call")}, {sweep.cost.tokens.toLocaleString("en-US")} tokens.
      </p>
      {sweep.proposals.length > 0 && (
        <Link
          className="font-medium underline underline-offset-2"
          to={`/cases/${encodeURIComponent(sweep.case_id ?? "")}/workspace?view=proposals`}
        >
          Review {plural(sweep.proposals.length, "item")} in Agent proposals
        </Link>
      )}
      <ol className="space-y-2">
        {sweep.outcome.expectations.map((e) => (
          <li key={e.id} className="rounded border p-2" data-testid="disconfirm-expectation">
            <p>{e.claim}</p>
            <p className="text-xs font-medium">
              {e.findings
                ? `${plural(e.findings, "item")} against this expectation, waiting for a person.`
                : e.sentence}
            </p>
            <details className="text-xs text-muted-foreground">
              <summary>What was searched, and what was out of reach</summary>
              <ul className="list-disc pl-5">
                {e.searched.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              {e.out_of_reach.length > 0 && (
                <>
                  <p className="mt-1 font-medium">Out of reach</p>
                  <ul className="list-disc pl-5" data-testid="disconfirm-out-of-reach">
                    {e.out_of_reach.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </>
              )}
            </details>
          </li>
        ))}
      </ol>
      {sweep.refused.length > 0 && (
        <div>
          <p className="font-medium">Found but not recorded</p>
          <ul className="list-disc pl-5 text-xs">
            {sweep.refused.map((r, i) => (
              <li key={i}>
                {r.title || "Untitled"}: {r.why}
              </li>
            ))}
          </ul>
        </div>
      )}
      {sweep.repeats.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {plural(sweep.repeats.length, "further item")} cited exactly the sources of an item already put to a person,
          so {sweep.repeats.length === 1 ? "it was" : "they were"} not asked again.
        </p>
      )}
      <AbsenceList title="What the theory needs and the case lacks" items={named} />
      <AbsenceList title="Accounts seen in the case with no statement" items={seen} />
      {!!sweep.absences?.not_checked?.length && (
        <div>
          <p className="font-medium">Could not be checked</p>
          <ul className="list-disc pl-5 text-xs">
            {sweep.absences.not_checked.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}
      {!!absences.length && <p className="text-xs text-muted-foreground">{sweep.absences?.limitation}</p>}
    </div>
  )
}

function AbsenceList({ title, items }: { title: string; items: NonNullable<DisconfirmSweep["absences"]>["items"] }) {
  if (!items.length) return null
  return (
    <div data-testid="disconfirm-absences">
      <p className="font-medium">
        {title} ({items.length})
      </p>
      <ul className="list-disc space-y-1 pl-5 text-xs">
        {items.map((a, i) => (
          <li key={i}>
            <span className="font-medium">{a.what}.</span> {a.reason}
            {a.why ? ` Why it is expected: ${a.why}` : ""}
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * Looks across the whole case for what breaks a theory: what it leads you to expect, what tells against each
 * expectation, and what the case lacks. The count of model reads is stated before they start. Each item waits in
 * Agent proposals for a person; an accepted one is shown here with the model that wrote it.
 */
export function DisconfirmPanel({ caseId, theoryId, canEdit }: { caseId: string; theoryId: string; canEdit: boolean }) {
  const client = useQueryClient()
  const key = [...agentProposalKeys.all(caseId), "disconfirm", theoryId]
  const state = useQuery({
    queryKey: key,
    queryFn: () => fetchDisconfirm(caseId, theoryId),
    refetchInterval: (query) => (isActive(query.state.data?.sweep) ? 2000 : false),
  })
  const refresh = () => client.invalidateQueries({ queryKey: agentProposalKeys.all(caseId) })
  // The answer is the sweep: shown at once, so the press does not wait for a second request to show progress.
  const shown = (answer: DisconfirmSweep) => {
    client.setQueryData<DisconfirmState>(key, (old) => (old ? { ...old, sweep: answer } : old))
    return refresh()
  }
  const plan = useMutation({ mutationFn: () => planDisconfirm(caseId, theoryId), onSuccess: shown })
  const start = useMutation({
    mutationFn: (limit?: number) => startDisconfirm(caseId, state.data?.sweep?.id ?? "", limit),
    onSuccess: shown,
  })
  const stop = useMutation({ mutationFn: () => stopDisconfirm(caseId, state.data?.sweep?.id ?? ""), onSuccess: refresh })
  const sweep = state.data?.sweep
  const active = isActive(sweep)
  const left = sweep ? sweep.reads.pending + sweep.reads.failed : 0
  const ready = !!sweep && !active && sweep.stage !== "planning" && left > 0
  const failure = plan.error || start.error || stop.error
  const counts = state.data?.tally
  return (
    <section className="space-y-2 rounded-lg border border-border p-3 text-sm" aria-label="What breaks this theory">
      <h3 className="text-sm font-semibold">What breaks this theory</h3>
      <p className="text-xs text-muted-foreground">
        Searches the whole case: the ledger, the phones, the documents and the graph. One model call works out what the
        theory leads you to expect. You then see the exact number of further calls before any is made. Each item found
        waits in Agent proposals for a person to accept or reject.
      </p>
      {counts && (
        <p data-testid="disconfirm-tally">
          Counter-arguments: {counts.counter_arguments.total} proposed, {counts.counter_arguments.accepted} accepted by a
          person, {counts.counter_arguments.rejected} rejected, {counts.counter_arguments.waiting} waiting. Red cell:{" "}
          {counts.red_cell.total} proposed, {counts.red_cell.accepted} accepted, {counts.red_cell.rejected} rejected,{" "}
          {counts.red_cell.waiting} waiting.
        </p>
      )}
      {!!state.data?.counter_arguments.length && (
        <div data-testid="counter-arguments">
          <p className="font-medium">Counter-arguments</p>
          <ul className="space-y-1">
            {state.data.counter_arguments.map((c) => (
              <li key={c.id} className="rounded border p-2">
                <p className="font-medium">{String(c.content.title ?? "")}</p>
                <p className="whitespace-pre-wrap text-xs">{c.person_text || c.model_text}</p>
                <p className="text-xs text-muted-foreground">
                  Written by {c.proposal.model || "a model"}, accepted by {c.accepted_by || "a person"}. A model's
                  reading of its cited sources.
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
      {(plan.isPending || start.isPending) && !active && (
        <p role="status" className="rounded border p-2 font-medium" data-testid="disconfirm-progress">
          Asking the server to start{plan.isPending ? " the sweep" : " the reads"}…
        </p>
      )}
      {sweep && active && <Progress sweep={sweep} />}
      {sweep?.error && (
        <p role="alert" data-testid="disconfirm-error">
          {sweep.error}
        </p>
      )}
      {sweep?.reads.failures.map((f) => (
        <p key={f.id} role="alert" className="text-xs">
          Read {f.id} did not finish: {f.error}
        </p>
      ))}
      {sweep && !active && sweep.stage === "done" && <Result sweep={sweep} />}
      {sweep?.stage === "planned" && !active && !!sweep.expectations.length && (
        <div>
          <p className="font-medium">What the theory leads you to expect ({sweep.expectations.length})</p>
          <ol className="list-decimal pl-5 text-xs">
            {sweep.expectations.map((e) => (
              <li key={e.id}>{e.claim}</li>
            ))}
          </ol>
        </div>
      )}
      {canEdit && ready && <Plan sweep={sweep} busy={start.isPending} onStart={(limit) => start.mutate(limit)} />}
      {canEdit && active && (
        <Button size="sm" variant="ghost" disabled={stop.isPending || sweep?.cancel_requested} onClick={() => stop.mutate()}>
          Stop
        </Button>
      )}
      {canEdit && !active && !ready && (
        <Button size="sm" variant="outline" disabled={plan.isPending} onClick={() => plan.mutate()}>
          {sweep ? "Sweep the case again (one model call)" : "Look for what breaks it (one model call)"}
        </Button>
      )}
      {failure && <p role="alert">{failure.message}</p>}
    </section>
  )
}
