import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { evidenceAPI } from "../api"

export function useFolderContents(caseId: string | undefined, folderId: string | null) {
  return useQuery({
    queryKey: ["folder-contents", caseId, folderId],
    queryFn: () => {
      if (folderId) {
        return evidenceAPI.getFolderContents(folderId)
      }
      // Root level: list folders + files at root
      return Promise.all([
        evidenceAPI.listFolders(caseId!),
        evidenceAPI.list(caseId!),
      ]).then(([folders, files]) => ({
        folder: null,
        breadcrumbs: [],
        folders: folders,
        files: files.filter((f) => !f.folder_id),
      }))
    },
    enabled: !!caseId,
  })
}

export function useCreateFolder(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ name, parentId }: { name: string; parentId?: string | null }) =>
      evidenceAPI.createFolder(caseId, name, parentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["folder-contents"] })
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] })
    },
  })
}

export function useRenameFolder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ folderId, name }: { folderId: string; name: string }) =>
      evidenceAPI.renameFolder(folderId, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["folder-contents"] })
    },
  })
}

export function useDeleteFolder(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (folderId: string) => evidenceAPI.deleteFolder(folderId, caseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["folder-contents"] })
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] })
    },
  })
}

export function useMoveFile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ evidenceId, newFolderId }: { evidenceId: string; newFolderId: string | null }) =>
      evidenceAPI.moveFile(evidenceId, newFolderId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["folder-contents"] })
      queryClient.invalidateQueries({ queryKey: ["evidence"] })
    },
  })
}

export function useMoveFolder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ folderId, newParentId }: { folderId: string; newParentId: string | null }) =>
      evidenceAPI.moveFolder(folderId, newParentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["folder-contents"] })
    },
  })
}
