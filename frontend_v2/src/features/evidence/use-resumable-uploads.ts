import { useQuery } from "@tanstack/react-query"
import { listUploads } from "./resumable-upload"
import { listUploadGroups } from "./resumable-upload-groups"

export function useResumableUploads(caseId: string) {
  return useQuery({
    queryKey: ["resumable-uploads", caseId],
    queryFn: () => listUploads(caseId),
    refetchInterval: 2000,
  })
}

export function useResumableUploadGroups(caseId: string) {
  return useQuery({
    queryKey: ["resumable-upload-groups", caseId],
    queryFn: () => listUploadGroups(caseId),
    refetchInterval: 2000,
  })
}
