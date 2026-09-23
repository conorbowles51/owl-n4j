import { useQuery } from "@tanstack/react-query"
import { listUploads } from "./resumable-upload"

export function useResumableUploads(caseId: string) {
  return useQuery({
    queryKey: ["resumable-uploads", caseId],
    queryFn: () => listUploads(caseId),
    refetchInterval: 2000,
  })
}
