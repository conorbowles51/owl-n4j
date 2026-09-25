import { useQuery } from "@tanstack/react-query"
import { listUploads } from "./resumable-upload"
import { listUploadGroups } from "./resumable-upload-groups"

export function useResumableUploads(caseId: string, active = true) {
  return useQuery({
    queryKey: ["resumable-uploads", caseId],
    queryFn: () => listUploads(caseId),
    enabled: active,
    refetchInterval: active ? 2000 : false,
  })
}

export function useResumableUploadGroups(caseId: string, active = true) {
  return useQuery({
    queryKey: ["resumable-upload-groups", caseId],
    queryFn: () => listUploadGroups(caseId),
    enabled: active,
    refetchInterval: active ? 2000 : false,
  })
}
