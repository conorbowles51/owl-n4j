import { useEffect, useState } from "react"
import { Bot, Loader2, X } from "lucide-react"
import { Button } from "@/components/ui/button"

function elapsedLabel(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000))
  const minutes = Math.floor(seconds / 60)
  return minutes ? `${minutes} min ${seconds % 60} s` : `${seconds} s`
}

/** The agent's running state: what it is doing, steps done, time so far, Cancel, and that leaving the page is safe. */
export function ThinkingBubble({
  status,
  startedAt = null,
  stepsDone = 0,
  onCancel,
}: {
  status?: string | null
  startedAt?: number | null
  stepsDone?: number
  onCancel?: () => void
}) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!startedAt) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [startedAt])
  const progress = [
    stepsDone ? `${stepsDone} ${stepsDone === 1 ? "step" : "steps"} done` : null,
    startedAt ? elapsedLabel(now - startedAt) : null,
  ]
    .filter(Boolean)
    .join(" · ")
  return (
    <div className="flex gap-3">
      <div className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
        <Bot className="size-4" />
      </div>
      <div className="flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-2 text-sm text-muted-foreground">
        <div className="space-y-0.5" role="status" aria-live="polite">
          <div className="flex items-center gap-2">
            <Loader2 className="size-4 animate-spin" />
            <span>{status || "Working through the case data"}</span>
            {progress && <span className="tabular-nums">· {progress}</span>}
          </div>
          <p className="text-xs">
            Long questions can take several minutes. It keeps running if you open another page; come back here for
            the answer.
          </p>
        </div>
        {onCancel && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={onCancel}
          >
            <X className="mr-1 size-3" />
            Cancel
          </Button>
        )}
      </div>
    </div>
  )
}
