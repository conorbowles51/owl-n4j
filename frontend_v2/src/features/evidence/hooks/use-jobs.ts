import { useQuery } from "@tanstack/react-query"
import type { EvidenceJob } from "@/types/evidence.types"

// For now, use the evidence engine jobs via the backend proxy
async function fetchJobs(caseId: string): Promise<EvidenceJob[]> {
  const { fetchAPI } = await import("@/lib/api-client")
  // Use the evidence engine's job listing
  const jobs = await fetchAPI<EvidenceJob[]>(`/api/evidence/engine/jobs?case_id=${caseId}`)
  // Engine reports progress as 0.0-1.0; frontend expects 0-100
  return jobs.map((job) => ({
    ...job,
    progress: job.progress <= 1 ? job.progress * 100 : job.progress,
  }))
}

const TERMINAL_JOB_STATUSES = new Set(["completed", "failed"])

/** True while any job can still change: everything that has not completed or failed, paused jobs included. */
export function hasUnfinishedJobs(jobs: Pick<EvidenceJob, "status">[] | undefined): boolean {
  return jobs?.some((job) => !TERMINAL_JOB_STATUSES.has(job.status)) ?? false
}

/** Poll interval for a watched job list: every 5 s while a job is unfinished or the last fetch failed, otherwise
 * every 60 s. The full list is several MB on a large case, so a list with nothing running is checked only once a
 * minute: often enough that a job started elsewhere (another user, a server-side reading or background task)
 * appears while the page stays open. Starting, retrying, pausing or resuming a job here invalidates the list at
 * once, and it is refetched on mount, focus and reconnect. */
export const IDLE_JOBS_POLL_MS = 60_000

export function jobsPollInterval(
  watch: boolean,
  jobs: EvidenceJob[] | undefined,
  failed = false
): number | false {
  if (!watch) return false
  return failed || hasUnfinishedJobs(jobs) ? 5000 : IDLE_JOBS_POLL_MS
}

export function useJobs(caseId: string | undefined, watch = false) {
  return useQuery({
    queryKey: ["evidence-jobs", caseId],
    queryFn: () => fetchJobs(caseId!),
    enabled: !!caseId,
    refetchOnMount: "always",
    refetchOnReconnect: true,
    refetchOnWindowFocus: true,
    refetchInterval: (query) =>
      jobsPollInterval(watch, query.state.data, query.state.status === "error"),
  })
}
