import { useEffect, useRef, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import type { EvidenceJob } from "@/types/evidence.types"
import { fetchJobs, hasUnfinishedJobs } from "@/features/evidence/hooks/use-jobs"
import { JOB_STARTED_EVENT } from "@/lib/job-started"
import { announce } from "./announce"
import type { ActionFacts } from "./next-steps"

/** Jobs that finish within this time of each other are told as one batch ("3 files processed"). */
export const BATCH_MS = 4000
const WATCH_POLL_MS = 10_000

export interface Finished {
  files: number
  names: number
  links: number
  failed: number
  fileName?: string
  evidenceId?: string
}

/** The document jobs that finished between two reads of the list (pure, for tests). */
export function finishedBetween(running: ReadonlySet<string>, jobs: EvidenceJob[]): { done: EvidenceJob[]; failed: EvidenceJob[] } {
  const done = jobs.filter((j) => running.has(j.id) && j.status === "completed")
  const failed = jobs.filter((j) => running.has(j.id) && j.status === "failed")
  return { done, failed }
}

export function processedFacts(done: EvidenceJob[], failed: EvidenceJob[]): ActionFacts & { kind: "document-processed" } {
  const one = done.length === 1 ? done[0] : null
  return {
    kind: "document-processed",
    files: done.length,
    names: done.reduce((n, j) => n + (j.entity_count || 0), 0),
    links: done.reduce((n, j) => n + (j.relationship_count || 0), 0),
    failed: failed.length,
    fileName: one?.file_name,
    evidenceId: one?.evidence_file_id ?? undefined,
  }
}

/**
 * Tells the person when document processing they can see finishes, wherever they are in the case (lx-guide B).
 * It reads the evidence job list only while a job is known to be unfinished (this tab started one, or another
 * screen's read showed one), so an idle case costs no requests; other screens' reads of the same list are used too.
 */
export function useEvidenceJobWatcher(caseId: string) {
  const qc = useQueryClient()
  const key = ["evidence-jobs", caseId]
  const [watching, setWatching] = useState(() => hasUnfinishedJobs(qc.getQueryData<EvidenceJob[]>(key)))
  const running = useRef<Set<string> | null>(null)
  const pending = useRef<{ done: EvidenceJob[]; failed: EvidenceJob[]; timer: number | null }>({ done: [], failed: [], timer: null })

  useQuery({
    queryKey: key,
    queryFn: () => fetchJobs(caseId),
    enabled: watching,
    refetchInterval: WATCH_POLL_MS,
    refetchOnMount: false,
    staleTime: WATCH_POLL_MS,
  })

  useEffect(() => {
    const p = pending.current
    const started = () => setWatching(true)
    window.addEventListener(JOB_STARTED_EVENT, started)
    const look = (jobs: EvidenceJob[] | undefined) => {
      if (!jobs) return
      if (running.current) {
        const { done, failed } = finishedBetween(running.current, jobs)
        if (done.length || failed.length) {
          p.done.push(...done)
          p.failed.push(...failed)
          if (p.timer) window.clearTimeout(p.timer)
          p.timer = window.setTimeout(() => {
            if (p.done.length) announce(caseId, processedFacts(p.done, p.failed))
            p.done = []
            p.failed = []
            p.timer = null
          }, BATCH_MS)
        }
      }
      running.current = new Set(jobs.filter((j) => j.status !== "completed" && j.status !== "failed").map((j) => j.id))
      setWatching(running.current.size > 0)
    }
    look(qc.getQueryData<EvidenceJob[]>(key))
    const unsub = qc.getQueryCache().subscribe((e) => {
      if (e.type === "updated" && e.action.type === "success" && e.query.queryKey[0] === "evidence-jobs" && e.query.queryKey[1] === caseId)
        look(e.query.state.data as EvidenceJob[] | undefined)
    })
    return () => {
      window.removeEventListener(JOB_STARTED_EVENT, started)
      unsub()
      if (p.timer) window.clearTimeout(p.timer)
    }
    // key is derived from caseId
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, qc])
}
