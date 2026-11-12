import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import type { EventFile } from "../api"

/** Every file attached to an event in this case, loaded once and shared by every card. */
export function useCaseEventFiles(caseId: string | undefined) {
  return useQuery({
    queryKey: ["timeline-event-files", caseId],
    queryFn: () =>
      fetchAPI<{ files: EventFile[] }>(
        `/api/timeline/event-files?${new URLSearchParams({ case_id: caseId! })}`
      ),
    enabled: !!caseId,
    staleTime: 30_000,
  })
}
