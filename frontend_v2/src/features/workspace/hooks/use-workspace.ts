import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  workspaceAPI,
  type Theory,
  type InvestigationTask,
  type Witness,
  type InvestigativeNote,
  type CaseContext,
  type PinnedItem,
} from "../api"

// ---------------------------------------------------------------------------
// Query key helpers
// ---------------------------------------------------------------------------

const keys = {
  all: (caseId: string) => ["workspace", caseId] as const,
  theories: (caseId: string) => ["workspace", caseId, "theories"] as const,
  tasks: (caseId: string) => ["workspace", caseId, "tasks"] as const,
  witnesses: (caseId: string) => ["workspace", caseId, "witnesses"] as const,
  notes: (caseId: string) => ["workspace", caseId, "notes"] as const,
  context: (caseId: string) => ["workspace", caseId, "context"] as const,
  pinned: (caseId: string) => ["workspace", caseId, "pinned"] as const,
  presence: (caseId: string) => ["workspace", caseId, "presence"] as const,
  timeline: (caseId: string) => ["workspace", caseId, "timeline"] as const,
}

export { keys as workspaceKeys }

// ---------------------------------------------------------------------------
// Theories
// ---------------------------------------------------------------------------

export function useTheories(caseId: string) {
  return useQuery({
    queryKey: keys.theories(caseId),
    queryFn: () => workspaceAPI.getTheories(caseId),
  })
}

export function useCreateTheory(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (theory: Omit<Theory, "id">) =>
      workspaceAPI.createTheory(caseId, theory),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.theories(caseId) }),
  })
}

export function useUpdateTheory(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      theoryId,
      updates,
    }: {
      theoryId: string
      updates: Partial<Theory>
    }) => workspaceAPI.updateTheory(caseId, theoryId, updates),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.theories(caseId) }),
  })
}

export function useDeleteTheory(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (theoryId: string) =>
      workspaceAPI.deleteTheory(caseId, theoryId),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.theories(caseId) }),
  })
}

export function useBuildTheoryGraph(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      theoryId,
      options,
    }: {
      theoryId: string
      options?: Record<string, unknown>
    }) => workspaceAPI.buildTheoryGraph(caseId, theoryId, options),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.theories(caseId) }),
  })
}

// ---------------------------------------------------------------------------
// Tasks
// ---------------------------------------------------------------------------

export function useTasks(caseId: string) {
  return useQuery({
    queryKey: keys.tasks(caseId),
    queryFn: () => workspaceAPI.getTasks(caseId),
  })
}

export function useCreateTask(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (task: Omit<InvestigationTask, "id">) =>
      workspaceAPI.createTask(caseId, task),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.tasks(caseId) }),
  })
}

export function useUpdateTask(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      taskId,
      updates,
    }: {
      taskId: string
      updates: Partial<InvestigationTask>
    }) => workspaceAPI.updateTask(caseId, taskId, updates),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.tasks(caseId) }),
  })
}

export function useDeleteTask(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (taskId: string) => workspaceAPI.deleteTask(caseId, taskId),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.tasks(caseId) }),
  })
}

// ---------------------------------------------------------------------------
// Witnesses
// ---------------------------------------------------------------------------

export function useWitnesses(caseId: string) {
  return useQuery({
    queryKey: keys.witnesses(caseId),
    queryFn: () => workspaceAPI.getWitnesses(caseId),
  })
}

export function useCreateWitness(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (witness: Omit<Witness, "id">) =>
      workspaceAPI.createWitness(caseId, witness),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: keys.witnesses(caseId) }),
  })
}

export function useUpdateWitness(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      witnessId,
      updates,
    }: {
      witnessId: string
      updates: Partial<Witness>
    }) => workspaceAPI.updateWitness(caseId, witnessId, updates),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: keys.witnesses(caseId) }),
  })
}

export function useDeleteWitness(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (witnessId: string) =>
      workspaceAPI.deleteWitness(caseId, witnessId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: keys.witnesses(caseId) }),
  })
}

// ---------------------------------------------------------------------------
// Notes
// ---------------------------------------------------------------------------

export function useNotes(caseId: string) {
  return useQuery({
    queryKey: keys.notes(caseId),
    queryFn: () => workspaceAPI.getNotes(caseId),
  })
}

export function useCreateNote(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (note: Omit<InvestigativeNote, "id">) =>
      workspaceAPI.createNote(caseId, note),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.notes(caseId) }),
  })
}

export function useUpdateNote(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      noteId,
      updates,
    }: {
      noteId: string
      updates: Partial<InvestigativeNote>
    }) => workspaceAPI.updateNote(caseId, noteId, updates),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.notes(caseId) }),
  })
}

export function useDeleteNote(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (noteId: string) => workspaceAPI.deleteNote(caseId, noteId),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.notes(caseId) }),
  })
}

// ---------------------------------------------------------------------------
// Case Context
// ---------------------------------------------------------------------------

export function useCaseContext(caseId: string) {
  return useQuery({
    queryKey: keys.context(caseId),
    queryFn: () => workspaceAPI.getCaseContext(caseId),
  })
}

export function useUpdateCaseContext(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (context: Partial<CaseContext>) =>
      workspaceAPI.updateCaseContext(caseId, context),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.context(caseId) }),
  })
}

// ---------------------------------------------------------------------------
// Pinned Items
// ---------------------------------------------------------------------------

export function usePinnedItems(caseId: string) {
  return useQuery({
    queryKey: keys.pinned(caseId),
    queryFn: () => workspaceAPI.getPinnedItems(caseId),
  })
}

export function usePinItem(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      itemType,
      itemId,
      annotationsCount,
    }: {
      itemType: string
      itemId: string
      annotationsCount?: number
    }) => workspaceAPI.pinItem(caseId, itemType, itemId, annotationsCount),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.pinned(caseId) }),
  })
}

export function useUnpinItem(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (pinId: string) => workspaceAPI.unpinItem(caseId, pinId),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.pinned(caseId) }),
  })
}

// ---------------------------------------------------------------------------
// Presence
// ---------------------------------------------------------------------------

export function usePresence(caseId: string) {
  return useQuery({
    queryKey: keys.presence(caseId),
    queryFn: () => workspaceAPI.getPresence(caseId),
    refetchInterval: 30_000,
  })
}

// ---------------------------------------------------------------------------
// Investigation Timeline
// ---------------------------------------------------------------------------

export function useInvestigationTimeline(caseId: string) {
  return useQuery({
    queryKey: keys.timeline(caseId),
    queryFn: () => workspaceAPI.getInvestigationTimeline(caseId),
  })
}
