import { useQuery } from "@tanstack/react-query"
import { FILE_PAGE_SIZE, foldersAPI, type FolderContentsParams } from "../folders.api"
import type { EvidenceSort } from "../utils/preferences"

/** The file list's page request for the list's state (FileListPanel and the start-up prefetch). */
export function folderContentsParams(state: {
  filePage: number
  statusFilter: string
  typeFilter: string
  sortBy: EvidenceSort["sort_by"]
  sortDirection: EvidenceSort["sort_direction"]
}) {
  return {
    limit: FILE_PAGE_SIZE,
    offset: state.filePage * FILE_PAGE_SIZE,
    status: state.statusFilter !== "all" ? state.statusFilter : undefined,
    type: state.typeFilter || undefined,
    sort_by: state.sortBy,
    sort_direction: state.sortDirection,
  }
}

/** Key and fetcher shared by the hook and the start-up prefetch (route-data.ts). */
export const folderContentsQuery = (
  caseId: string | undefined,
  folderId: string | null,
  params: FolderContentsParams = {}
) => ({
  queryKey: ["evidence-folder-contents", caseId, folderId, params],
  queryFn: ({ signal }: { signal: AbortSignal }) =>
    foldersAPI.getContents(caseId!, folderId, params, signal),
})

export function useFolderContents(
  caseId: string | undefined,
  folderId: string | null,
  params: FolderContentsParams = {}
) {
  return useQuery({
    ...folderContentsQuery(caseId, folderId, params),
    enabled: !!caseId,
    refetchInterval: query => query.state.data?.files.some(file => file.status === 'processing') ? 3000 : false,
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
    refetchInterval: query => query.state.data?.files.some(file => file.status === 'processing') ? 3000 : false,
  })
}
