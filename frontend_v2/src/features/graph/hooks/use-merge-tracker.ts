import { useState, useRef, useCallback, useEffect } from "react"
import { announce } from "@/features/guidance/announce"
import { guidanceQueryClient } from "@/features/guidance/query-client"
import { labelFromCache } from "@/features/guidance/label"
import { graphAPI } from "../api"
import { useGraphStore } from "@/stores/graph.store"
import { toast } from "sonner"

export interface MergeTrackerJob {
  engineJobId: string
  mergeJobId: string
  sourceEntityKeys: string[]
  status: string
  progress: number
  message: string
  error?: string
  /** The merged record is not in meaning search or duplicate checks yet; the backfill fills it in. */
  searchPending?: boolean
}

export const SEARCH_PENDING_NOTE =
  "The merged record is not in search yet. It is added automatically when the search service is back; until then, duplicate checks may miss it."

interface UseMergeTrackerOptions {
  onCompleted?: () => void
  onPartial?: () => void
}

/** Next steps after a merge (lx-guide B): the merged entry on the graph and the timeline. */
function announceMerge(mergedKey: string | null, sourceKeys: string[]) {
  const caseId = /^\/cases\/([^/]+)/.exec(window.location.pathname)?.[1]
  const qc = guidanceQueryClient()
  const name = (mergedKey && qc && labelFromCache(qc, mergedKey)) || "one entry"
  announce(caseId ? decodeURIComponent(caseId) : null, { kind: "merge-done", name, entityKey: mergedKey, merged: sourceKeys.length })
}

export function useMergeTracker({ onCompleted, onPartial }: UseMergeTrackerOptions = {}) {
  const [activeJob, setActiveJob] = useState<MergeTrackerJob | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const mergeJobPollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const dialogOpenRef = useRef(false)
  const callbacksRef = useRef({ onCompleted, onPartial })

  useEffect(() => {
    callbacksRef.current = { onCompleted, onPartial }
  }, [onCompleted, onPartial])

  const stopTracking = useCallback(() => {
    wsRef.current?.close()
    wsRef.current = null
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    if (mergeJobPollRef.current) {
      clearInterval(mergeJobPollRef.current)
      mergeJobPollRef.current = null
    }
  }, [])

  const handleMergeJobUpdate = useCallback(
    (data: { status: string; error_message?: string | null; search_pending?: boolean | null; merged_entity_key?: string | null }, sourceKeys: string[]) => {
      const searchPending = data.search_pending === true
      if (data.status === "completed") {
        stopTracking()
        announceMerge(data.merged_entity_key ?? null, sourceKeys)
        setActiveJob((prev) =>
          prev ? { ...prev, status: "completed", progress: 100, message: "Merge complete!", searchPending } : null
        )
        callbacksRef.current.onCompleted?.()
        if (!dialogOpenRef.current) {
          if (searchPending) toast.success("Merge complete", { description: SEARCH_PENDING_NOTE })
          else toast.success("Merge complete")
        }
      } else if (data.status === "partial") {
        stopTracking()
        const store = useGraphStore.getState()
        for (const key of sourceKeys) {
          store.unhideNode(key)
        }
        setActiveJob((prev) =>
          prev
            ? {
                ...prev,
                status: "partial",
                progress: 100,
                message: "Merge completed with warnings",
                error: data.error_message || "Some source entities could not be removed.",
                searchPending,
              }
            : null
        )
        callbacksRef.current.onPartial?.()
        if (!dialogOpenRef.current) {
          toast.warning("Merge completed with warnings — some source entities remain")
        }
      } else if (data.status === "failed") {
        stopTracking()
        const store = useGraphStore.getState()
        for (const key of sourceKeys) {
          store.unhideNode(key)
        }
        setActiveJob((prev) =>
          prev
            ? {
                ...prev,
                status: "failed",
                message: "Merge failed",
                error: data.error_message || "Merge failed",
              }
            : null
        )
      }
    },
    [stopTracking]
  )

  const startMergeJobPolling = useCallback(
    (mergeJobId: string, sourceKeys: string[]) => {
      if (mergeJobPollRef.current) return
      mergeJobPollRef.current = setInterval(async () => {
        try {
          const job = await graphAPI.getMergeJob(mergeJobId)
          if (job.status === "completed" || job.status === "partial" || job.status === "failed") {
            handleMergeJobUpdate(job, sourceKeys)
          }
        } catch {
          // keep polling
        }
      }, 2000)
    },
    [handleMergeJobUpdate]
  )

  const handleEngineUpdate = useCallback(
    (
      data: { status: string; progress?: number; message?: string; error_message?: string },
      mergeJobId: string,
      sourceKeys: string[]
    ) => {
      const pct = Math.round((data.progress ?? 0) * 100)

      if (data.status === "completed") {
        // Engine done — hide source entities optimistically and start stage-2 polling
        const store = useGraphStore.getState()
        for (const key of sourceKeys) {
          store.hideNode(key)
        }

        // Stop engine polling, switch to MergeJob polling
        wsRef.current?.close()
        wsRef.current = null
        if (pollRef.current) {
          clearInterval(pollRef.current)
          pollRef.current = null
        }

        setActiveJob((prev) =>
          prev
            ? { ...prev, status: "completing", progress: 95, message: "Cleaning up source entities..." }
            : null
        )
        startMergeJobPolling(mergeJobId, sourceKeys)
      } else if (data.status === "failed") {
        stopTracking()
        setActiveJob((prev) =>
          prev
            ? {
                ...prev,
                status: "failed",
                progress: pct,
                message: "Merge failed",
                error: data.error_message || data.message || "Merge failed",
              }
            : null
        )
      } else {
        setActiveJob((prev) =>
          prev ? { ...prev, status: data.status, progress: pct, message: data.message || "" } : null
        )
      }
    },
    [startMergeJobPolling, stopTracking]
  )

  const startTracking = useCallback(
    (engineJobId: string, mergeJobId: string, sourceEntityKeys: string[]) => {
      stopTracking()

      setActiveJob({
        engineJobId,
        mergeJobId,
        sourceEntityKeys,
        status: "pending",
        progress: 0,
        message: "Queued...",
      })

      // Start engine job polling (3s)
      pollRef.current = setInterval(async () => {
        try {
          const job = await graphAPI.getEngineJob(engineJobId)
          handleEngineUpdate(job, mergeJobId, sourceEntityKeys)
        } catch {
          // keep polling
        }
      }, 3000)

      // Try WebSocket for real-time engine updates
      try {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
        const wsUrl = `${protocol}//${window.location.host}/api/evidence/ws/jobs/${engineJobId}`
        const ws = new WebSocket(wsUrl)
        wsRef.current = ws

        ws.onmessage = (event) => {
          try {
            handleEngineUpdate(JSON.parse(event.data), mergeJobId, sourceEntityKeys)
          } catch {
            // ignore parse errors
          }
        }

        ws.onerror = () => {
          ws.close()
          wsRef.current = null
        }
        ws.onclose = () => {
          wsRef.current = null
        }
      } catch {
        // WebSocket unavailable — polling handles it
      }
    },
    [stopTracking, handleEngineUpdate]
  )

  const clearJob = useCallback(() => {
    stopTracking()
    setActiveJob(null)
  }, [stopTracking])

  const setDialogOpen = useCallback((open: boolean) => {
    dialogOpenRef.current = open
  }, [])

  useEffect(() => {
    return () => stopTracking()
  }, [stopTracking])

  return { activeJob, startTracking, clearJob, setDialogOpen }
}
