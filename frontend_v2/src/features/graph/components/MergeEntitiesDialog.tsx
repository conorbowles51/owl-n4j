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
  const [preferredType, setPreferredType] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Job progress state
  const [jobId, setJobId] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)
  const [statusMessage, setStatusMessage] = useState("")
  const [jobStatus, setJobStatus] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  // Reset state when dialog opens
  useEffect(() => {
    if (!open) return
    setPreferredName("")
    setPreferredType("")
    setSubmitting(false)
    setError(null)
    setJobId(null)
    setProgress(0)
    setStatusMessage("")
    setJobStatus(null)
  }, [open])

  // Cleanup WebSocket on unmount or close
  useEffect(() => {
    return () => {
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [])

  const connectToJob = useCallback(
    (jid: string) => {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
      const wsUrl = `${protocol}//${window.location.host}/api/evidence/ws/jobs/${jid}`

      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          setProgress(Math.round((data.progress ?? 0) * 100))
          setStatusMessage(STATUS_LABELS[data.status] || data.message || "")
          setJobStatus(data.status)

          if (data.status === "completed") {
            ws.close()
            wsRef.current = null
            setTimeout(() => {
              onMerged?.()
              onOpenChange(false)
            }, 1500)
          } else if (data.status === "failed") {
            ws.close()
            wsRef.current = null
            setError(data.error_message || data.message || "Merge failed")
          }
        } catch {
          // ignore parse errors
        }
      }

      ws.onerror = () => {
        ws.close()
        wsRef.current = null
        setError("Connection lost. The merge may still be running — refresh to check.")
        setJobStatus("failed")
      }
    },
    [onMerged, onOpenChange]
  )

  const handleMerge = async () => {
    if (!entity1 || !entity2) return
    setSubmitting(true)
    setError(null)

    try {
      const result = await graphAPI.mergeEntities(
        caseId,
        [entity1.key, entity2.key],
        preferredName.trim() || undefined,
        preferredType.trim() || undefined
      )
      setJobId(result.job_id)
      setJobStatus("pending")
      setStatusMessage(STATUS_LABELS.pending)
      connectToJob(result.job_id)
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
    <Dialog open={open} onOpenChange={(v) => { if (!isProcessing || isFailed) onOpenChange(v) }}>
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
            {[entity1, entity2].map((entity, i) => (
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

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">
                  Preferred type (optional)
                </label>
                <Input
                  value={preferredType}
                  onChange={(e) => setPreferredType(e.target.value)}
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
                {progress}%
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
