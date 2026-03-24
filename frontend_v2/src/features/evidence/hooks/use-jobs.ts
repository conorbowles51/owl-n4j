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

export function useJobs(caseId: string | undefined, hasActiveJobs = false) {
  return useQuery({
    queryKey: ["evidence-jobs", caseId],
    queryFn: () => fetchJobs(caseId!),
    enabled: !!caseId,
    // Poll every 5s when there are active jobs
    refetchInterval: hasActiveJobs ? 5000 : false,
  })
}
