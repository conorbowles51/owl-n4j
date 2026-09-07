import { useQuery } from "@tanstack/react-query"
import { foldersAPI, type FolderContentsParams } from "../folders.api"

export function useFolderContents(
  caseId: string | undefined,
  folderId: string | null,
  params: FolderContentsParams = {}
) {
  return useQuery({
    queryKey: ["evidence-folder-contents", caseId, folderId, params],
    queryFn: ({ signal }) =>
      foldersAPI.getContents(caseId!, folderId, params, signal),
    enabled: !!caseId,
  })
}

export function useFilenameSearch(
  caseId: string,
  query: string,
  scope: "case" | "subtree",
  folderId: string | null,
  params: FolderContentsParams,
  enabled: boolean
) {
  return useQuery({
    // Shares the listing cache prefix so every existing mutation and processing update refreshes results.
    queryKey: [
      "evidence-folder-contents",
      caseId,
      "search",
      scope,
      folderId,
      query,
      params,
    ],
    queryFn: ({ signal }) =>
      foldersAPI.search(caseId, query, scope, folderId, params, signal),
    enabled: enabled && query.length > 0,
  })
}
