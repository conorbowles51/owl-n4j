import { useQuery } from "@tanstack/react-query"
import { foldersAPI, type FolderContentsParams } from "../folders.api"

export function useFolderContents(
  caseId: string | undefined,
  folderId: string | null,
  params: FolderContentsParams = {}
) {
  return useQuery({
    queryKey: ["evidence-folder-contents", caseId, folderId, params],
    queryFn: () => foldersAPI.getContents(caseId!, folderId, params),
    enabled: !!caseId,
  })
}
