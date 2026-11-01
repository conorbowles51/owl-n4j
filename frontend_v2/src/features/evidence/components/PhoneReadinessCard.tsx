import { useEffect, useState } from "react"
import { AlertCircle, CheckCircle2, Circle, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/cn"
import type { EvidenceJob, PhoneJobState } from "@/types/evidence.types"
import { FIRST_RUN_INLINE, formatTimeLeft } from "../upload-progress"
import {
  CANCEL_KEEPS,
  measureOf,
  n,
  observe,
  outcomeLines,
  PHONE_STALL_SECONDS,
  PHONE_STEPS,
  stepIndex,
  stepText,
} from "../phone-readiness"

function useTick(active: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [active])
  return now
}

interface Props {
  job: EvidenceJob
  onPause?: (job: EvidenceJob) => void
  onResume?: (job: EvidenceJob) => void
  onCancel?: (job: EvidenceJob) => void
  onClear?: (job: EvidenceJob) => void
  controlling?: boolean
}

export function PhoneReadinessCard({ job, onPause, onResume, onCancel, onClear, controlling = false }: Props) {
  const phone: PhoneJobState = job.pipeline_state?.phone || {}
  const isFailed = job.status === "failed"
  const isCompleted = job.status === "completed"
  const isActive = !isFailed && !isCompleted
  const now = useTick(isActive && !job.paused)
  const stage = job.stage || phone.stage
  const counts = job.counts || phone.counts
  const current = isCompleted ? PHONE_STEPS.length : stepIndex(stage)
  const seen = isActive && stage ? observe(job.id, stage, counts, now) : null
  const serverChange = phone.changed_at ? Date.parse(phone.changed_at) : 0
  // The last change the server recorded or this browser saw; with neither, the time this card first saw the step.
  const lastChange = Math.max(seen?.changedAt ?? 0, serverChange || 0) || seen?.firstSeen || 0
  const stalledFor = isActive && !job.paused && lastChange ? Math.floor((now - lastChange) / 1000) : 0
  const [confirmCancel, setConfirmCancel] = useState(false)
  const cancelled = !!phone.cancelled
  const notReadable = phone.state === "not_readable"
  const held = phone.state === "reconciliation_failed"
  const message = isFailed ? job.error_message || phone.message : phone.message || job.message
  const stepWord = PHONE_STEPS[Math.min(current, PHONE_STEPS.length - 1)].label

  return (
    <div
      role="group"
      aria-label={`Phone report: ${job.file_name}`}
      className={cn(
        "rounded-lg border bg-card p-3",
        (isFailed || held) && "border-red-500/20",
        isCompleted && !held && "border-green-500/20"
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm font-medium">Getting {job.file_name || "the phone report"} ready</span>
        {isCompleted && !held && !notReadable ? <CheckCircle2 className="size-3.5 shrink-0 text-green-500" /> : null}
        {isFailed || held || notReadable ? <AlertCircle className="size-3.5 shrink-0 text-red-500" /> : null}
      </div>

      <ol className="mt-2 space-y-1">
        {PHONE_STEPS.map((step, i) => {
          const done = i < current && !cancelled
          const running = i === current && isActive
          return (
            <li key={step.key} className="text-xs">
              <span className="flex items-center gap-1.5">
                {done ? (
                  <CheckCircle2 className="size-3 text-green-500" />
                ) : running && !job.paused ? (
                  <Loader2 className="size-3 animate-spin text-blue-500" />
                ) : (
                  <Circle className="size-3 text-muted-foreground/50" />
                )}
                <span className={cn(done || running ? "text-foreground" : "text-muted-foreground")}>{step.label}</span>
                {done ? <span className="text-muted-foreground">: done</span> : null}
                {running && job.paused ? <span className="text-muted-foreground">: paused</span> : null}
              </span>
              {running && !job.paused ? (
                <span className="ml-[18px] block text-[11px] text-muted-foreground" aria-live="polite">
                  {stepText(stage, counts)}
                  {measureOf(stage, counts) ? `, ${seen?.left != null ? formatTimeLeft(seen.left) : FIRST_RUN_INLINE}` : ""}
                </span>
              ) : null}
            </li>
          )
        })}
      </ol>

      {isActive && !job.paused ? (
        <div className="mt-2 flex items-center gap-2">
          <Progress value={job.progress} className="h-1.5 flex-1" />
          <span className="text-[10px] font-mono tabular-nums text-muted-foreground">{Math.min(99, Math.round(job.progress))}%</span>
        </div>
      ) : null}

      {stalledFor >= PHONE_STALL_SECONDS ? (
        <p className="mt-2 text-[11px] text-amber-700 dark:text-amber-400">
          No change on {stepWord.toLowerCase()} for {n(stalledFor)} s. The server is still on this step. Last change at{" "}
          {new Date(lastChange).toLocaleTimeString()}.
        </p>
      ) : null}

      {!isActive && message ? <p className="mt-2 text-xs">{message}</p> : null}
      {isCompleted && !notReadable
        ? outcomeLines(phone.file_outcomes).map((line) => (
            <p key={line} className="text-[11px] text-muted-foreground">
              {line}
            </p>
          ))
        : null}
      {isFailed && !cancelled ? (
        <p className="mt-1 text-[11px] text-muted-foreground">
          {phone.failure_stage ? `Stopped at: ${stepWord}. ` : ""}Reference {phone.reference || job.id}
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {isActive && !job.paused && onPause ? (
          <Button size="sm" variant="outline" className="h-7 text-[11px]" disabled={controlling || job.pause_requested} onClick={() => onPause(job)}>
            {job.pause_requested ? "Pausing" : "Pause"}
          </Button>
        ) : null}
        {(job.paused || (isFailed && !cancelled)) && job.resumable && onResume ? (
          <Button size="sm" variant="outline" className="h-7 text-[11px]" disabled={controlling} onClick={() => onResume(job)}>
            {isFailed ? "Try again" : "Resume"}
          </Button>
        ) : null}
        {(isActive || (isFailed && !cancelled)) && onCancel && !phone.cancel_requested ? (
          <Button size="sm" variant="ghost" className="h-7 text-[11px]" disabled={controlling} onClick={() => setConfirmCancel(true)}>
            Cancel
          </Button>
        ) : null}
        {phone.cancel_requested && isActive ? <span className="text-[11px] text-muted-foreground">Cancelling after the current step saves</span> : null}
        {!isActive && onClear ? (
          <Button size="sm" variant="ghost" className="h-7 text-[11px] text-muted-foreground" onClick={() => onClear(job)}>
            Clear
          </Button>
        ) : null}
      </div>
      {confirmCancel ? (
        <div role="alertdialog" aria-label="Cancel this reading" className="mt-2 rounded-md border p-2 text-[11px]">
          <p>{CANCEL_KEEPS}</p>
          <div className="mt-2 flex gap-2">
            <Button
              size="sm"
              variant="danger"
              className="h-7 text-[11px]"
              onClick={() => {
                setConfirmCancel(false)
                onCancel?.(job)
              }}
            >
              Cancel the reading
            </Button>
            <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={() => setConfirmCancel(false)}>
              Keep reading
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
