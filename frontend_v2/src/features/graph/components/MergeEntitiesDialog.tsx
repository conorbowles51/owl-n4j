import { useState, useEffect } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NodeBadge } from "@/components/ui/node-badge"
import { Progress } from "@/components/ui/progress"
import type { GraphNode } from "@/types/graph.types"
import { graphAPI } from "../api"
import type { MergeTrackerJob } from "../hooks/use-merge-tracker"
import { GitMerge, AlertTriangle, Loader2, CheckCircle2, XCircle } from "lucide-react"

/* ── Props ── */

interface MergeEntitiesDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  entities: GraphNode[]
  caseId: string
  similarity?: number
  activeJob: MergeTrackerJob | null
  onStartTracking: (engineJobId: string, mergeJobId: string, sourceEntityKeys: string[]) => void
  onClearJob: () => void
}

/* ── Status label mapping ── */

const STATUS_LABELS: Record<string, string> = {
  pending: "Queued...",
  merging_properties: "AI is merging properties...",
  writing_graph: "Writing merged entity to graph...",
  completing: "Cleaning up source entities...",
  completed: "Merge complete!",
  partial: "Merge completed with warnings",
  failed: "Merge failed",
}

/* ── Main component ── */

export function MergeEntitiesDialog({
  open,
  onOpenChange,
  entities,
  caseId,
  similarity,
  activeJob,
  onStartTracking,
  onClearJob,
}: MergeEntitiesDialogProps) {
  const [preferredName, setPreferredName] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setPreferredName("")
      setSubmitting(false)
      setError(null)
    }
  }, [open])

  const handleMerge = async () => {
    if (entities.length < 2) return
    setSubmitting(true)
    setError(null)

    try {
      const result = await graphAPI.mergeEntities(
        caseId,
        entities.map((e) => e.key),
        preferredName.trim() || undefined
      )
      onStartTracking(
        result.job_id,
        result.merge_job_id,
        entities.map((e) => e.key)
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start merge")
      setSubmitting(false)
    }
  }

  if (entities.length < 2) return null

  const status = activeJob?.status
  const isProcessing = activeJob !== null && status !== "failed" && status !== "partial"
  const isComplete = status === "completed"
  const isFailed = status === "failed"
  const isPartial = status === "partial"
  const isTerminal = isComplete || isFailed || isPartial
  const statusMessage = status ? STATUS_LABELS[status] || activeJob?.message || "" : ""
  const progress = activeJob?.progress ?? 0
  const displayError = error || activeJob?.error

  const handleClose = () => {
    if (isTerminal) onClearJob()
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-lg">
            <GitMerge className="h-5 w-5" />
            Merge Entities
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Entity cards */}
          <div className="flex flex-wrap gap-2">
            {entities.map((entity) => (
              <div
                key={entity.key}
                className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5"
              >
                <NodeBadge type={entity.type} />
                <span className="text-xs font-medium truncate max-w-[140px]">
                  {entity.label}
                </span>
              </div>
            ))}
          </div>

          {/* Options (hidden during processing) */}
          {!activeJob && !isFailed && (
            <>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">
                  Preferred name (optional — AI will decide if left blank)
                </label>
                <Input
                  value={preferredName}
                  onChange={(e) => setPreferredName(e.target.value)}
                  placeholder="Leave blank for AI to choose"
                />
              </div>

              {/* Warning */}
              <div className="flex items-start gap-2.5 rounded-md border border-amber-500/30 bg-amber-500/10 p-3">
                <AlertTriangle className="h-4 w-4 shrink-0 text-amber-700 dark:text-amber-400 mt-0.5" />
                <div className="text-xs text-amber-700 dark:text-amber-400">
                  <p className="font-medium">AI-powered merge</p>
                  <p className="mt-0.5 opacity-80">
                    AI will intelligently merge all properties from {entities.length} entities into one.
                    The originals will be moved to the recycle bin.
                  </p>
                </div>
              </div>
            </>
          )}

          {/* Progress (shown during processing) */}
          {isProcessing && (
            <div className="space-y-3 py-2">
              <div className="flex items-center gap-2">
                {isComplete ? (
                  <CheckCircle2 className="h-5 w-5 text-emerald-500" />
                ) : (
                  <Loader2 className="h-5 w-5 animate-spin text-amber-500" />
                )}
                <span className="text-sm font-medium">
                  {statusMessage}
                </span>
              </div>
              <Progress value={progress} className="h-2" />
              <p className="text-xs text-muted-foreground text-center">
                {progress}% — you can close this dialog, the merge will continue in the background
              </p>
            </div>
          )}

          {/* Completed */}
          {isComplete && (
            <div className="flex items-center gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
              <p className="text-xs text-emerald-700 dark:text-emerald-400">Merge complete!</p>
            </div>
          )}

          {/* Partial success warning */}
          {isPartial && (
            <div className="flex items-start gap-2.5 rounded-md border border-amber-500/30 bg-amber-500/10 p-3">
              <AlertTriangle className="h-4 w-4 shrink-0 text-amber-700 dark:text-amber-400 mt-0.5" />
              <div className="text-xs text-amber-700 dark:text-amber-400">
                <p className="font-medium">Merge completed with warnings</p>
                <p className="mt-0.5 opacity-80">
                  Entities merged successfully, but some source entities could not be removed.
                  You may see duplicates — check the recycle bin.
                </p>
              </div>
            </div>
          )}

          {/* Error */}
          {(displayError || isFailed) && (
            <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3">
              <XCircle className="h-4 w-4 shrink-0 text-destructive mt-0.5" />
              <p className="text-xs text-destructive">{displayError}</p>
            </div>
          )}
        </div>

        <DialogFooter>
          {!activeJob && (
            <>
              <Button variant="outline" onClick={handleClose}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleMerge}
                disabled={submitting}
                className="gap-1.5"
              >
                <GitMerge className="h-3.5 w-3.5" />
                {submitting ? "Starting..." : "Merge with AI"}
              </Button>
            </>
          )}
          {isTerminal && (
            <Button variant="outline" onClick={handleClose}>
              Close
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
