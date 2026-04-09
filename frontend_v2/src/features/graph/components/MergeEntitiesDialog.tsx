import { useState, useEffect, useRef, useCallback } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NodeBadge } from "@/components/ui/node-badge"
import { Progress } from "@/components/ui/progress"
import type { GraphNode } from "@/types/graph.types"
import { graphAPI } from "../api"
import { GitMerge, AlertTriangle, Loader2, CheckCircle2, XCircle } from "lucide-react"

/* ── Props ── */

interface MergeEntitiesDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  entity1: GraphNode | null
  entity2: GraphNode | null
  caseId: string
  similarity?: number
  onMerged?: () => void
}

/* ── Status label mapping ── */

const STATUS_LABELS: Record<string, string> = {
  pending: "Queued...",
  merging_properties: "AI is merging properties...",
  writing_graph: "Writing merged entity to graph...",
  completed: "Merge complete!",
  failed: "Merge failed",
}

/* ── Main component ── */

export function MergeEntitiesDialog({
  open,
  onOpenChange,
  entity1,
  entity2,
  caseId,
  similarity,
  onMerged,
}: MergeEntitiesDialogProps) {
  const [preferredName, setPreferredName] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Job progress state
  const [jobId, setJobId] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)
  const [statusMessage, setStatusMessage] = useState("")
  const [jobStatus, setJobStatus] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Stop all tracking (WebSocket + polling)
  const stopTracking = useCallback(() => {
    wsRef.current?.close()
    wsRef.current = null
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  // Handle a progress update from either WebSocket or polling
  const handleUpdate = useCallback(
    (data: { status: string; progress?: number; message?: string; error_message?: string }) => {
      const pct = Math.round((data.progress ?? 0) * 100)
      setProgress(pct)
      setStatusMessage(STATUS_LABELS[data.status] || data.message || "")
      setJobStatus(data.status)

      if (data.status === "completed") {
        stopTracking()
        setTimeout(() => {
          onMerged?.()
          onOpenChange(false)
        }, 1500)
      } else if (data.status === "failed") {
        stopTracking()
        setError(data.error_message || data.message || "Merge failed")
      }
    },
    [onMerged, onOpenChange, stopTracking]
  )

  // Start polling fallback
  const startPolling = useCallback(
    (jid: string) => {
      if (pollRef.current) return
      pollRef.current = setInterval(async () => {
        try {
          const job = await graphAPI.getEngineJob(jid)
          handleUpdate(job)
        } catch {
          // Polling error — keep trying
        }
      }, 3000)
    },
    [handleUpdate]
  )

  // Connect WebSocket + start polling fallback
  const trackJob = useCallback(
    (jid: string) => {
      // Always start polling as a reliable fallback
      startPolling(jid)

      // Try WebSocket for real-time updates
      try {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
        const wsUrl = `${protocol}//${window.location.host}/api/evidence/ws/jobs/${jid}`
        const ws = new WebSocket(wsUrl)
        wsRef.current = ws

        ws.onmessage = (event) => {
          try {
            handleUpdate(JSON.parse(event.data))
          } catch {
            // ignore parse errors
          }
        }

        ws.onerror = () => {
          // WebSocket failed — polling fallback will handle it
          ws.close()
          wsRef.current = null
        }

        ws.onclose = () => {
          wsRef.current = null
        }
      } catch {
        // WebSocket not available — polling handles it
      }
    },
    [handleUpdate, startPolling]
  )

  // Reset state when dialog opens; refresh graph if closed during/after a merge
  useEffect(() => {
    if (open) {
      setPreferredName("")
      setSubmitting(false)
      setError(null)
      setJobId(null)
      setProgress(0)
      setStatusMessage("")
      setJobStatus(null)
    } else if (jobId) {
      // Dialog closed while a merge job was running or just completed — refresh
      stopTracking()
      onMerged?.()
    }
  }, [open])

  // Cleanup on unmount
  useEffect(() => {
    return () => stopTracking()
  }, [stopTracking])

  const handleMerge = async () => {
    if (!entity1 || !entity2) return
    setSubmitting(true)
    setError(null)

    try {
      const result = await graphAPI.mergeEntities(
        caseId,
        [entity1.key, entity2.key],
        preferredName.trim() || undefined
      )
      setJobId(result.job_id)
      setJobStatus("pending")
      setStatusMessage(STATUS_LABELS.pending)
      trackJob(result.job_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start merge")
      setSubmitting(false)
    }
  }

  if (!entity1 || !entity2) return null

  const isProcessing = jobId !== null && jobStatus !== "failed"
  const isComplete = jobStatus === "completed"
  const isFailed = jobStatus === "failed"

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-lg">
            <GitMerge className="h-5 w-5" />
            Merge Entities
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Entity cards */}
          <div className="grid grid-cols-2 gap-3">
            {[entity1, entity2].map((entity) => (
              <div
                key={entity.key}
                className="rounded-lg border border-border p-3"
              >
                <div className="flex items-center gap-1.5 mb-1">
                  <NodeBadge type={entity.type} />
                </div>
                <p className="text-sm font-medium leading-tight truncate">
                  {entity.label}
                </p>
              </div>
            ))}
          </div>

          {/* Options (hidden during processing) */}
          {!isProcessing && !isFailed && (
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
                    AI will intelligently merge all properties from both entities.
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

          {/* Error */}
          {(error || isFailed) && (
            <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3">
              <XCircle className="h-4 w-4 shrink-0 text-destructive mt-0.5" />
              <p className="text-xs text-destructive">{error}</p>
            </div>
          )}
        </div>

        <DialogFooter>
          {!isProcessing && (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
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
          {isFailed && (
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Close
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
