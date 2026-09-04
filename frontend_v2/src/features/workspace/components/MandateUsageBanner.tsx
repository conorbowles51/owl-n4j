import { useState } from "react"
import { BookOpenCheck, ChevronDown, ChevronUp, RefreshCw } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

interface Props {
  versionNumber?: number | null
  activeVersionNumber?: number | null
  stale?: boolean
  incomplete?: boolean
  temporaryOverride: string
  onTemporaryOverrideChange: (value: string) => void
  onAdoptCurrent?: () => Promise<void> | void
}

export function MandateUsageBanner({
  versionNumber,
  activeVersionNumber,
  stale,
  incomplete,
  temporaryOverride,
  onTemporaryOverrideChange,
  onAdoptCurrent,
}: Props) {
  const [overrideOpen, setOverrideOpen] = useState(false)
  const [adopting, setAdopting] = useState(false)
  const adopt = async () => {
    if (!onAdoptCurrent) return
    setAdopting(true)
    try { await onAdoptCurrent() } finally { setAdopting(false) }
  }

  return <div className={`border-b px-4 py-2 ${stale ? "border-amber-500/20 bg-amber-500/5" : "border-border bg-muted/10"}`}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex items-center gap-2 text-xs">
        <BookOpenCheck className={`size-3.5 ${incomplete ? "text-muted-foreground" : "text-violet-500"}`} />
        {incomplete ? <span className="text-muted-foreground">No saved case mandate</span> : <><span className="font-medium">Using case mandate</span><Badge variant="secondary">v{versionNumber}</Badge></>}
        {temporaryOverride.trim() && <Badge variant="outline">Request override</Badge>}
        {stale && <span className="text-amber-700 dark:text-amber-300">A newer version {activeVersionNumber ? `(v${activeVersionNumber})` : ""} is active.</span>}
      </div>
      <div className="flex items-center gap-1">
        {stale && onAdoptCurrent && <Button variant="ghost" size="sm" onClick={adopt} disabled={adopting}><RefreshCw className={`size-3.5 ${adopting ? "animate-spin" : ""}`} /> Adopt current</Button>}
        <Button variant="ghost" size="sm" onClick={() => setOverrideOpen((value) => !value)}>Override for next request {overrideOpen ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}</Button>
      </div>
    </div>
    {overrideOpen && <div className="mt-2 max-w-2xl"><Textarea aria-label="Temporary mandate override" value={temporaryOverride} onChange={(event) => onTemporaryOverrideChange(event.target.value)} rows={2} placeholder="Optional instructions for the next request only. This will not change the saved mandate." /><p className="mt-1 text-[10px] text-muted-foreground">Applied as temporary perspective / posture and cleared after the request is sent.</p></div>}
  </div>
}
