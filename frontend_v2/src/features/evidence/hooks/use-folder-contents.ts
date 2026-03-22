import { useQuery } from "@tanstack/react-query"
import { foldersAPI } from "../folders.api"

export function useFolderContents(caseId: string | undefined, folderId: string | null) {
  return useQuery({
    queryKey: ["evidence-folder-contents", caseId, folderId],
    queryFn: () => foldersAPI.getContents(caseId!, folderId),
    enabled: !!caseId,
  })
}
