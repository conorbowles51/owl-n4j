import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { failureText } from "@/features/phones/api"
import { getThreadReviewState, presenceBeat, recordSecondPass, type SecondPassState } from "@/features/phones/review-share"

/** One beat per open thread every 45 s (under 1 per 30 s), none while the tab is hidden; the server forgets a
 * person 100 s after their last beat, and at once when they leave the thread. */
export const PRESENCE_BEAT_MS = 45_000

export function useThreadPresence(caseId: string, threadKey: string | null | undefined) {
  const [words, setWords] = useState<string | null>(null)
  useEffect(() => {
    setWords(null)
    if (!caseId || !threadKey) return
    let live = true
    const beat = () => {
      if (typeof document !== "undefined" && document.hidden) return
      Promise.resolve()
        .then(() => presenceBeat(caseId, threadKey))
        .then((r) => live && setWords(r?.words ?? null))
        .catch(() => live && setWords(null)) // presence is a courtesy: a failed beat never blocks reading
    }
    beat()
    const timer = setInterval(beat, PRESENCE_BEAT_MS)
    return () => {
      live = false
      clearInterval(timer)
      Promise.resolve().then(() => presenceBeat(caseId, threadKey, true)).catch(() => undefined)
    }
  }, [caseId, threadKey])
  return words
}

/**
 * Under the open thread's header: "[name] is also reviewing this thread." (07 J-13 failure state), the review task
 * the thread is in, and any second-pass sample it is in, with Agrees / Disagrees for the second reviewer (step 5).
 */
export function ThreadReviewBar({ caseId, threadKey }: { caseId: string; threadKey: string }) {
  const also = useThreadPresence(caseId, threadKey)
  const q = useQuery({
    queryKey: ["phone-thread-review", caseId, threadKey],
    queryFn: () => getThreadReviewState(caseId, threadKey),
    enabled: !!caseId && !!threadKey,
  })
  const tasks = q.data?.tasks ?? []
  const samples = q.data?.second_pass ?? []
  if (!also && !tasks.length && !samples.length) return null
  return (
    <div data-testid="thread-review-bar" className="flex flex-col gap-1 border-b px-3 py-1.5 text-xs">
      {also && <p role="status" data-testid="also-reviewing" className="font-medium text-status-review">{also}</p>}
      {tasks.map((t) => (
        <p key={t.task_id}>In review task "{t.title}"{t.assigned_to_name ? `, assigned to ${t.mine ? "you" : t.assigned_to_name}` : ""}.</p>
      ))}
      {samples.map((s) => <SecondPassRow key={s.task_id} caseId={caseId} threadKey={threadKey} s={s} />)}
    </div>
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
    onError: (e) => setError(failureText(e, "The second-pass result could not be saved.")),
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
