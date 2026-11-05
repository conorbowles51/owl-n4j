import { useQuery } from "@tanstack/react-query"
import { foldersAPI } from "../folders.api"

export const folderTreeQuery = (caseId: string | undefined) => ({
  queryKey: ["evidence-folder-tree", caseId],
  queryFn: () => foldersAPI.getTree(caseId!),
})

export function useFolderTree(caseId: string | undefined) {
  return useQuery({ ...folderTreeQuery(caseId), enabled: !!caseId })
}
