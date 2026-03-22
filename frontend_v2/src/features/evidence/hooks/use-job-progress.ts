import { useEffect, useRef, useCallback } from "react"
import { useQueryClient } from "@tanstack/react-query"
import type { EvidenceJob, JobProgressMessage } from "@/types/evidence.types"

interface UseJobProgressOptions {
  /** Case ID for cache invalidation */
  caseId: string | undefined
  /** List of active job IDs to monitor via WebSocket */
  jobIds: string[]
  /** Called when a job reaches a terminal state */
  onComplete?: (jobId: string) => void
  /** Called when a job fails */
  onError?: (jobId: string, error: string) => void
}

/**
 * WebSocket hook that connects to the evidence engine's job progress
 * endpoint for real-time updates. Falls back gracefully if WebSocket
 * is unavailable (the useJobs hook handles polling fallback).
 */
export function useJobProgress(options: UseJobProgressOptions) {
  const { caseId, jobIds, onComplete, onError } = options
  const queryClient = useQueryClient()
  const socketsRef = useRef<Map<string, WebSocket>>(new Map())
  const retriesRef = useRef<Map<string, number>>(new Map())

  const handleMessage = useCallback(
    (jobId: string, data: JobProgressMessage) => {
      // Update the job in the React Query cache
      queryClient.setQueryData<EvidenceJob[]>(
        ["evidence-jobs", caseId],
        (old) => {
          if (!old) return old
          return old.map((job) =>
            job.id === jobId
              ? {
                  ...job,
                  status: data.status as EvidenceJob["status"],
                  progress: data.progress,
                }
              : job
          )
        }
      )

      // Handle terminal states
      if (data.status === "completed") {
        queryClient.invalidateQueries({
          queryKey: ["evidence-folder-contents", caseId],
        })
        queryClient.invalidateQueries({
          queryKey: ["evidence-folder-tree", caseId],
        })
        onComplete?.(jobId)
      } else if (data.status === "failed") {
        queryClient.invalidateQueries({
          queryKey: ["evidence-folder-contents", caseId],
        })
        onError?.(jobId, data.message || "Processing failed")
      }
    },
    [caseId, queryClient, onComplete, onError]
  )

  const connectToJob = useCallback(
    (jobId: string) => {
      // Don't connect if already connected
      if (socketsRef.current.has(jobId)) return

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
      const wsUrl = `${protocol}//${window.location.host}/api/evidence/ws/jobs/${jobId}`

      try {
        const ws = new WebSocket(wsUrl)
        socketsRef.current.set(jobId, ws)

        ws.onmessage = (event) => {
          try {
            const data: JobProgressMessage = JSON.parse(event.data)
            handleMessage(jobId, data)

            // Close socket on terminal status
            if (data.status === "completed" || data.status === "failed") {
              ws.close()
              socketsRef.current.delete(jobId)
              retriesRef.current.delete(jobId)
            }
          } catch {
            // Ignore parse errors
          }
        }

        ws.onclose = () => {
          socketsRef.current.delete(jobId)
        }

        ws.onerror = () => {
          ws.close()
          socketsRef.current.delete(jobId)

          // Retry with exponential backoff (max 3 attempts)
          const retries = retriesRef.current.get(jobId) || 0
          if (retries < 3) {
            retriesRef.current.set(jobId, retries + 1)
            const delay = Math.pow(2, retries) * 1000 // 1s, 2s, 4s
            setTimeout(() => connectToJob(jobId), delay)
          }
        }
      } catch {
        // WebSocket not available — polling fallback handles it
      }
    },
    [handleMessage]
  )

  useEffect(() => {
    // Connect to new jobs
    for (const jobId of jobIds) {
      if (!socketsRef.current.has(jobId)) {
        connectToJob(jobId)
      }
    }

    // Disconnect from removed jobs
    for (const [jobId, ws] of socketsRef.current) {
      if (!jobIds.includes(jobId)) {
        ws.close()
        socketsRef.current.delete(jobId)
        retriesRef.current.delete(jobId)
      }
    }
  }, [jobIds, connectToJob])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      for (const ws of socketsRef.current.values()) {
        ws.close()
      }
      socketsRef.current.clear()
      retriesRef.current.clear()
    }
  }, [])

  return {
    connectedCount: socketsRef.current.size,
  }
}
