import { Button } from "@/components/ui/button"
import type { WholeCaseRun } from "../lib/whole-case-run"

/**
 * A stored whole-case run on its way: which step of how many, and true counts where the step has them. A run that
 * stopped or failed says so and offers to run again; nothing partial is shown.
 */
export function WholeCaseProgress({
  run,
  error,
  noun,
  onAgain,
}: {
  run: WholeCaseRun<unknown> | undefined
  error: Error | null
  noun: string
  onAgain: () => void
}) {
  if (error)
    return (
      <div role="alert" className="space-y-2">
        <p>The whole-case run could not start. {error.message}</p>
        <Button onClick={onAgain}>Run the whole case again</Button>
      </div>
    )
  if (!run) return <p role="status">Starting the whole-case {noun}…</p>
  if (run.status === "failed" || run.status === "stopped")
    return (
      <div role="alert" className="space-y-2">
        <p>{run.error}</p>
        <Button onClick={onAgain}>Run the whole case again</Button>
      </div>
    )
  if (run.status === "completed") return null
  const parts = run.steps || 3
  const within = run.total ? Math.min(run.done / run.total, 1) : 0
  const share = Math.round(((Math.max(run.step - 1, 0) + within) / parts) * 100)
  return (
    <div role="status" className="space-y-1 rounded border p-3">
      <p>
        This scope is too large for one answer, so the whole {noun} is running
        in the background. You can keep working; the result stays here.
      </p>
      <p className="font-medium">
        {run.step ? `Step ${run.step} of ${parts}: ` : ""}
        {run.phase}
        {run.total ? ` (${run.done.toLocaleString("en-US")} of ${run.total.toLocaleString("en-US")})` : ""}
      </p>
      <div
        role="progressbar"
        aria-label={`Whole-case ${noun} progress`}
        aria-valuenow={share}
        aria-valuemin={0}
        aria-valuemax={100}
        className="h-2 w-full rounded bg-muted"
      >
        <div className="h-2 rounded bg-primary" style={{ width: `${share}%` }} />
      </div>
    </div>
  )
}

/** "1–25 of 12,408" with its two buttons: the count is the stored count of the whole list. */
export function WholeCasePager({
  label,
  offset,
  size,
  total,
  onOffset,
}: {
  label: string
  offset: number
  size: number
  total: number
  onOffset: (offset: number) => void
}) {
  if (total <= size) return null
  return (
    <div className="flex items-center gap-2 text-sm">
      <Button size="sm" disabled={!offset} onClick={() => onOffset(Math.max(0, offset - size))}>
        Previous {label}
      </Button>
      <span>
        {(offset + 1).toLocaleString("en-US")}–{Math.min(total, offset + size).toLocaleString("en-US")} of{" "}
        {total.toLocaleString("en-US")}
      </span>
      <Button size="sm" disabled={offset + size >= total} onClick={() => onOffset(offset + size)}>
        Next {label}
      </Button>
    </div>
  )
}
