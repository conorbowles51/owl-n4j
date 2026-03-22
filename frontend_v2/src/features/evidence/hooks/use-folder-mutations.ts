import { useMutation, useQueryClient } from "@tanstack/react-query"
import { foldersAPI } from "../folders.api"

export function useCreateFolder(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { name: string; parentId?: string | null }) =>
      foldersAPI.create(caseId, data.name, data.parentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["evidence-folder-tree", caseId] })
      qc.invalidateQueries({ queryKey: ["evidence-folder-contents", caseId] })
    },
  })
}

export function useRenameFolder(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { folderId: string; name: string }) =>
      foldersAPI.rename(data.folderId, data.name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["evidence-folder-tree", caseId] })
      qc.invalidateQueries({ queryKey: ["evidence-folder-contents", caseId] })
    },
  })
}

export function useDeleteFolder(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (folderId: string) => foldersAPI.delete(folderId, caseId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["evidence-folder-tree", caseId] })
      qc.invalidateQueries({ queryKey: ["evidence-folder-contents", caseId] })
    },
  })
}

export function useMoveFolder(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { folderId: string; newParentId: string | null }) =>
      foldersAPI.move(data.folderId, data.newParentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["evidence-folder-tree", caseId] })
      qc.invalidateQueries({ queryKey: ["evidence-folder-contents", caseId] })
    },
  })
}

export function useMoveFile(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { fileId: string; newFolderId: string | null }) =>
      foldersAPI.moveFile(data.fileId, data.newFolderId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["evidence-folder-tree", caseId] })
      qc.invalidateQueries({ queryKey: ["evidence-folder-contents", caseId] })
    },
  })
}
