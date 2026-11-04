import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState, type RefObject } from "react"
import { Button } from "@/components/ui/button"
import { getThreadReviewState, recordSecondPass, shareFailure, type ReviewPosition, type SecondPassState } from "@/features/phones/review-share"
import { HandOverDialog } from "./HandOverDialog"
import { useReadingPosition, type ReadRow } from "./use-reading-position"
import { useThreadPresence } from "./use-thread-presence"
import { instantWords } from "@/features/phones/lib/time-words"

/**
 * Under the open thread's header: "[name] is also reviewing this thread." (07 J-13 failure state), the review task
 * the thread is in, and any second-pass sample it is in, with Agrees / Disagrees for the second reviewer (step 5). An
 * assigned review keeps its position on the task (J-15): anyone opening the thread can go on from it, and Hand over
 * passes the task with a note.
 */
export function ThreadReviewBar({ caseId, threadKey, extraction, readRow, onResume, canEdit = true }: {
  caseId: string
  threadKey: string
  extraction: string | null
  readRow: RefObject<ReadRow | null>
  onResume: (eventUid: string) => void
  canEdit?: boolean
}) {
  const also = useThreadPresence(caseId, threadKey)
  const q = useQuery({
    queryKey: ["phone-thread-review", caseId, threadKey],
    queryFn: () => getThreadReviewState(caseId, threadKey),
    enabled: !!caseId && !!threadKey,
  })
  const tasks = q.data?.tasks ?? []
  const samples = q.data?.second_pass ?? []
  const assigned = [...tasks, ...samples].some((t) => t.mine && t.status !== "done")
  useReadingPosition(caseId, threadKey, extraction, readRow, assigned)
  const [handing, setHanding] = useState<{ id: string; title: string } | null>(null)
  if (!also && !tasks.length && !samples.length) return null
  return (
    <div data-testid="thread-review-bar" className="flex flex-col gap-1 border-b px-3 py-1.5 text-xs">
      {also && <p role="status" data-testid="also-reviewing" className="font-medium text-status-review">{also}</p>}
      {tasks.map((t) => (
        <div key={t.task_id} className="flex flex-wrap items-center gap-2">
          <p>In review task "{t.title}"{t.assigned_to_name ? `, assigned to ${t.mine ? "you" : t.assigned_to_name}` : ""}.</p>
          <TaskActions position={t.position} canHand={canEdit && t.status !== "done"} onResume={onResume} onHand={() => setHanding({ id: t.task_id, title: t.title })} />
        </div>
      ))}
      {samples.map((s) => (
        <div key={s.task_id} className="flex flex-wrap items-center gap-2">
          <SecondPassRow caseId={caseId} threadKey={threadKey} s={s} />
          <TaskActions position={s.position} canHand={canEdit && s.status !== "done"} onResume={onResume} onHand={() => setHanding({ id: s.task_id, title: s.title })} />
        </div>
      ))}
      {handing && <HandOverDialog caseId={caseId} taskId={handing.id} title={handing.title} open onClose={() => setHanding(null)} />}
    </div>
  )
}

function TaskActions({ position, canHand, onResume, onHand }: { position?: ReviewPosition | null; canHand: boolean; onResume: (eventUid: string) => void; onHand: () => void }) {
  return (
    <>
      {position && (
        <Button size="sm" variant="outline" onClick={() => onResume(position.event_uid)}>
          Continue where {position.by_name} stopped{position.instant ? ` (${instantWords(position.instant, "UTC")})` : ""}
        </Button>
      )}
      {canHand && <Button size="sm" variant="outline" onClick={onHand}>Hand over…</Button>}
    </>
  )
}

function SecondPassRow({ caseId, threadKey, s }: { caseId: string; threadKey: string; s: SecondPassState }) {
  const qc = useQueryClient()
  const [note, setNote] = useState("")
  const [error, setError] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: (agrees: boolean) => recordSecondPass(caseId, s.task_id, threadKey, agrees, note),
    onSuccess: () => {
      setError(null)
      setNote("")
      void qc.invalidateQueries({ queryKey: ["phone-thread-review", caseId, threadKey] })
      void qc.invalidateQueries({ queryKey: ["phone-review-coverage"] })
    },
    onError: (e) => setError(shareFailure(e, "The second-pass result could not be saved.")),
  })
  const first = s.first.reviewed_by_name ?? "a person"
  return (
    <div data-testid="second-pass" className="flex flex-wrap items-center gap-2">
      <span>{s.words} First review by {first}{s.first.record_count != null ? ` (${s.first.record_count.toLocaleString("en-US")} messages)` : ""}, kept as it is.</span>
      {s.mine && (
        <>
          <input
            aria-label="Second-pass note"
            className="h-7 min-w-48 rounded border px-2"
            placeholder="Note (needed to disagree)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <Button size="sm" variant="outline" disabled={save.isPending} onClick={() => save.mutate(true)}>Agrees</Button>
          <Button size="sm" variant="outline" disabled={save.isPending || !note.trim()} onClick={() => save.mutate(false)}
            title={!note.trim() ? "Say why you disagree" : undefined}>Disagrees</Button>
        </>
      )}
      {error && <span role="alert">{error}</span>}
    </div>
  )
}
