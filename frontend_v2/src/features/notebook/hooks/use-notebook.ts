import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  notebookAPI,
  type NotebookListParams,
  type NotebookNoteInput,
  type NotebookNoteUpdate,
  type NotebookTargetType,
} from "../api"

export const notebookKeys = {
  case: (caseId: string | undefined) => ["notebook", caseId] as const,
  list: (caseId: string | undefined, params: NotebookListParams) =>
    ["notebook", caseId, "notes", params] as const,
  target: (
    caseId: string | undefined,
    targetType: NotebookTargetType | undefined,
    targetId: string | undefined
  ) => ["notebook", caseId, "target", targetType, targetId] as const,
}

export function useNotebookNotes(
  caseId: string | undefined,
  params: NotebookListParams = {}
) {
  return useQuery({
    queryKey: notebookKeys.list(caseId, params),
    queryFn: () => notebookAPI.listNotes(caseId!, params),
    enabled: !!caseId,
  })
}

export function useTargetNotebookNotes(
  caseId: string | undefined,
  targetType: NotebookTargetType | undefined,
  targetId: string | undefined,
  limit = 20
) {
  return useQuery({
    queryKey: notebookKeys.target(caseId, targetType, targetId),
    queryFn: () => notebookAPI.listTargetNotes(caseId!, targetType!, targetId!, limit),
    enabled: !!caseId && !!targetType && !!targetId,
  })
}

export function useCreateNotebookNote(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: NotebookNoteInput) => notebookAPI.createNote(caseId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notebookKeys.case(caseId) })
    },
  })
}

export function useUpdateNotebookNote(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ noteId, input }: { noteId: string; input: NotebookNoteUpdate }) =>
      notebookAPI.updateNote(caseId, noteId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notebookKeys.case(caseId) })
    },
  })
}

export function useDeleteNotebookNote(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (noteId: string) => notebookAPI.deleteNote(caseId, noteId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notebookKeys.case(caseId) })
    },
  })
}
