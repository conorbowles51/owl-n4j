import { Bot, Loader2, RotateCcw, Square, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { formatElapsed, progressLine, useElapsedSeconds } from "../agent-run-progress"
import type { AgentRunNavigationState } from "../stores/agent-run.store"

export function AgentRunProgress({
  run,
  onStop,
  onRetry,
  onDismiss,
}: {
  run: AgentRunNavigationState
  onStop?: () => void
  onRetry?: () => void
  onDismiss?: () => void
}) {
  const elapsed = useElapsedSeconds(run.startedAt, !run.stale)
  if (run.stale) {
    return (
      <div className="flex gap-3" role="status" aria-live="polite">
        <div className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
          <Bot className="size-4" />
        </div>
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-500/40 bg-card px-3 py-2 text-sm">
          <span>
            This run stopped responding after {formatElapsed(elapsed)}, so it will not finish. Nothing already saved
            is lost.
          </span>
          {onRetry && (
            <Button type="button" size="sm" variant="secondary" className="h-7 px-2 text-xs" onClick={onRetry}>
              <RotateCcw className="mr-1 size-3" />
              Retry
            </Button>
          )}
          {onDismiss && (
            <Button type="button" size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={onDismiss}>
              <X className="mr-1 size-3" />
              Dismiss
            </Button>
          )}
        </div>
      </div>
    )
  }
  return (
    <div className="flex gap-3" role="status" aria-live="polite">
      <div className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
        <Bot className="size-4" />
      </div>
      <div
        className={
          run.progress?.phase === "retrying"
            ? "flex items-center gap-3 rounded-lg border border-amber-500/50 bg-card px-3 py-2 text-sm text-foreground"
            : "flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-2 text-sm text-muted-foreground"
        }
        data-phase={run.progress?.phase}
      >
        <div className="space-y-0.5">
          <div className="flex items-center gap-2" data-testid="agent-run-progress">
            <Loader2 className="size-4 shrink-0 animate-spin" />
            <span>{progressLine(run, elapsed)}</span>
          </div>
          <p className="text-xs">
            Long questions can take several minutes. It keeps running if you leave this page; come back here for the
            answer.
          </p>
        </div>
        {onStop && (
          <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={onStop}>
            <Square className="mr-1 size-3" />
            Stop
          </Button>
        )}
      </div>
    </div>
  )
}

/** The thread's last question has no answer and nothing is running for it: the run was stopped or did not finish.
 * The stored thread has no record of why, so the note says both and offers to ask again. */
export function AgentUnansweredNote({ onRetry }: { onRetry?: () => void }) {
  return (
    <div className="flex gap-3" role="status" data-testid="agent-unanswered-note">
      <div className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
        <Bot className="size-4" />
      </div>
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card px-3 py-2 text-sm text-muted-foreground">
        <span>No answer: this question was stopped before it finished. Nothing already saved is lost.</span>
        {onRetry && (
          <Button type="button" size="sm" variant="secondary" className="h-7 px-2 text-xs" onClick={onRetry}>
            <RotateCcw className="mr-1 size-3" />
            Ask again
          </Button>
        )}
      </div>
    </div>
  )
}
