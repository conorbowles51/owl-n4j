import { useState } from "react"
import { Loader2 } from "lucide-react"

import { formatElapsed, useElapsedSeconds } from "@/features/agent/agent-run-progress"

/** What a person reads while a chat answer is on its way: what is happening and for how long, never a bare spinner. */
export function ChatWaitingLine({ className = "" }: { className?: string }) {
  const [startedAtMs] = useState(() => Date.now())
  const elapsed = useElapsedSeconds(startedAtMs)
  return (
    <div className={`flex items-center gap-2 text-sm text-muted-foreground ${className}`} role="status" aria-live="polite">
      <Loader2 className="size-3.5 shrink-0 animate-spin text-amber-500" />
      <span>Searching the case and writing an answer · {formatElapsed(elapsed)} so far</span>
    </div>
  )
}
