import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import type { BackgroundTask } from "@/types/evidence.types"

async function fetchBackgroundTasks(caseId: string): Promise<BackgroundTask[]> {
  const params = new URLSearchParams({ case_id: caseId, limit: "50" })
  const response = await fetchAPI<{ tasks: BackgroundTask[] }>(
    `/api/background-tasks?${params}`
  )
  return response.tasks
}

export function useBackgroundTasks(caseId: string | undefined, poll = false) {
  return useQuery({
    queryKey: ["background-tasks", caseId],
    queryFn: () => fetchBackgroundTasks(caseId!),
    enabled: !!caseId,
    refetchOnMount: "always",
    refetchOnReconnect: true,
    refetchOnWindowFocus: true,
    refetchInterval: poll ? 5000 : false,
  })
}
