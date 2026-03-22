import { useQuery } from "@tanstack/react-query"
import { foldersAPI } from "../folders.api"

export function useFolderTree(caseId: string | undefined) {
  return useQuery({
    queryKey: ["evidence-folder-tree", caseId],
    queryFn: () => foldersAPI.getTree(caseId!),
    enabled: !!caseId,
  })
}
