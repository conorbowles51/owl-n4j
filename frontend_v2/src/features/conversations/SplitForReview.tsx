import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { caseMembersAPI } from "@/features/cases/members-api"
import { failureText, type StreamFilter } from "@/features/phones/api"
import { makeSplit, previewSplit, shareFailure, type SplitBy, type SplitMade, type SplitPlan } from "@/features/phones/review-share"
import { fmt } from "@/features/phones/ui/count-sentence"

/**
 * "Split for review" (07 J-13 step 1): the threads under the current filter go into Workspace tasks, one per chosen
 * person, by thread or by person. The counts are shown before anything is made; if the threads change in between,
 * nothing is made and the new counts are asked for.
 */
export function SplitForReview({ caseId, filter, scopeWords, open, onClose }: {
  caseId: string
  filter: StreamFilter
  scopeWords: string
  open: boolean
  onClose: () => void
}) {
  const qc = useQueryClient()
  const membersQ = useQuery({ queryKey: ["case-members", caseId], queryFn: () => caseMembersAPI.list(caseId), enabled: open && !!caseId })
  // only people who can mark threads reviewed (owners and editors) are offered
  const members = (membersQ.data ?? []).filter((m) => m.preset !== "viewer")
  const [chosen, setChosen] = useState<string[]>([])
  const [by, setBy] = useState<SplitBy>("thread")
  const [onlyNot, setOnlyNot] = useState(true)
  const [plan, setPlan] = useState<SplitPlan | null>(null)
  const [made, setMade] = useState<SplitMade | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const body = { filter, by, reviewers: chosen, only_not_reviewed: onlyNot, scope_words: scopeWords }

  const preview = useMutation({
    mutationFn: () => previewSplit(body),
    onSuccess: (p) => { setPlan(p); setNote(null) },
    onError: (e) => setNote(shareFailure(e, "The split could not be counted.")),
  })
  const create = useMutation({
    mutationFn: () => makeSplit({ ...body, expect_threads: plan!.threads }),
    onSuccess: (m) => {
      setMade(m)
      setNote(null)
      void qc.invalidateQueries({ queryKey: ["phone-review-coverage"] })
      void qc.invalidateQueries({ queryKey: ["phone-thread-review"] })
    },
    onError: (e) => {
      setNote(shareFailure(e, "The review tasks could not be made."))
      setPlan(null) // a 409 says the threads changed: count again before making anything
    },
  })
  const change = (fn: () => void) => { fn(); setPlan(null); setMade(null) }
  const close = () => { setPlan(null); setMade(null); setNote(null); onClose() }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Split for review</DialogTitle>
          <DialogDescription>
            The threads under this filter ({scopeWords || "every thread in the case"}) go into one Workspace task per person. Marks made in a task count in the case's review coverage.
          </DialogDescription>
        </DialogHeader>
        {made ? (
          <div role="status" data-testid="split-made" className="flex flex-col gap-2 text-sm">
            <p>{made.words}</p>
            <ul className="list-disc pl-4">
              {made.tasks.map((t) => (
                <li key={t.task_id}>{t.title}: {t.reviewer.name}, {fmt(t.threads)} {t.threads === 1 ? "thread" : "threads"}, {fmt(t.messages)} {t.messages === 1 ? "message" : "messages"}</li>
              ))}
            </ul>
            <Link className="underline" to={`/cases/${encodeURIComponent(caseId)}/workspace`}>Open the tasks in Workspace</Link>
          </div>
        ) : (
          <div className="flex flex-col gap-3 text-sm">
            <fieldset>
              <legend className="font-medium">Split</legend>
              <label className="mr-4 inline-flex items-center gap-1">
                <input type="radio" name="split-by" checked={by === "thread"} onChange={() => change(() => setBy("thread"))} /> by thread
              </label>
              <label className="inline-flex items-center gap-1">
                <input type="radio" name="split-by" checked={by === "person"} onChange={() => change(() => setBy("person"))} /> by person (each person's one-to-one threads to one reviewer)
              </label>
            </fieldset>
            <fieldset>
              <legend className="font-medium">Reviewers</legend>
              {membersQ.isLoading && <p role="status">Loading the case's members.</p>}
              {membersQ.isError && <p role="alert">{failureText(membersQ.error, "The case's members could not be loaded.")}</p>}
              {members.map((m) => (
                <label key={m.user_id} className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={chosen.includes(m.user_id)}
                    onChange={(e) => change(() => setChosen(e.target.checked ? [...chosen, m.user_id] : chosen.filter((x) => x !== m.user_id)))}
                  />
                  {m.user_name}
                </label>
              ))}
              {membersQ.data && members.length === 0 && <p>No member of this case can mark threads reviewed.</p>}
            </fieldset>
            <label className="inline-flex items-center gap-1">
              <input type="checkbox" checked={onlyNot} onChange={(e) => change(() => setOnlyNot(e.target.checked))} /> Leave out threads already fully reviewed or in an open review task
            </label>
            {plan && (
              <div data-testid="split-counts" className="rounded border p-2">
                <p>{plan.words}</p>
                <ul className="list-disc pl-4">
                  {plan.parts.map((p) => <li key={p.part}>{p.words}</li>)}
                </ul>
                {plan.warning && <p className="text-status-review">{plan.warning}</p>}
              </div>
            )}
          </div>
        )}
        {note && <p role="alert" className="text-sm">{note}</p>}
        <DialogFooter>
          {made ? (
            <Button onClick={close}>Close</Button>
          ) : plan ? (
            <Button disabled={create.isPending || plan.threads === 0} onClick={() => create.mutate()}>
              {create.isPending ? "Making the tasks" : `Make ${fmt(plan.parts.filter((p) => p.threads > 0).length)} review tasks`}
            </Button>
          ) : (
            <Button disabled={chosen.length === 0 || preview.isPending} onClick={() => preview.mutate()}>
              {preview.isPending ? "Counting" : chosen.length === 0 ? "Choose who reviews" : "Show the counts"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
