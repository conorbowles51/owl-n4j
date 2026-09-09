import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  workspaceAPI,
  type InvestigationTaskCreate,
  type TaskStatus,
  type CaseContextUpdate,
  type MandateVersionCreate,
} from "../api"

// ---------------------------------------------------------------------------
// Query key helpers
// ---------------------------------------------------------------------------

const keys = {
  tasks: (caseId: string) => ["workspace", caseId, "tasks"] as const,
  work: (caseId: string) => ["workspace", caseId, "work"] as const,
  context: (caseId: string) => ["workspace", caseId, "context"] as const,
  mandates: (caseId: string) => ["workspace", caseId, "context", "mandates"] as const,
  pinned: (caseId: string) => ["workspace", caseId, "pinned"] as const,
  overview: (caseId: string, timezoneName: string) =>
    ["workspace", caseId, "overview", timezoneName] as const,
}

export { keys as workspaceKeys }

function browserTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
  } catch {
    return "UTC"
  }
}

export function useWorkspaceOverview(caseId: string) {
  const timezoneName = browserTimezone()
  return useQuery({
    queryKey: keys.overview(caseId, timezoneName),
    queryFn: () => workspaceAPI.getOverview(caseId, timezoneName),
  })
}

export function useSetAttentionState(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      attentionKey,
      action,
      snoozedUntil,
    }: {
      attentionKey: string
      action: "dismiss" | "snooze"
      snoozedUntil?: string
    }) =>
      workspaceAPI.setAttentionState(caseId, attentionKey, {
        action,
        snoozed_until: snoozedUntil,
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["workspace", caseId, "overview"] }),
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
    mutationFn: (task: InvestigationTaskCreate) =>
      workspaceAPI.createTask(caseId, task),
    onSuccess: () => Promise.all([
      qc.invalidateQueries({ queryKey: keys.tasks(caseId) }),
      qc.invalidateQueries({ queryKey: keys.work(caseId) }),
      qc.invalidateQueries({ queryKey: ["workspace", caseId, "overview"] }),
    ]),
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
      updates: Partial<InvestigationTaskCreate>
    }) => workspaceAPI.updateTask(caseId, taskId, updates),
    onSuccess: () => Promise.all([
      qc.invalidateQueries({ queryKey: keys.tasks(caseId) }),
      qc.invalidateQueries({ queryKey: keys.work(caseId) }),
      qc.invalidateQueries({ queryKey: ["workspace", caseId, "overview"] }),
    ]),
  })
}

export function useDeleteTask(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (taskId: string) => workspaceAPI.deleteTask(caseId, taskId),
    onSuccess: () => Promise.all([
      qc.invalidateQueries({ queryKey: keys.tasks(caseId) }),
      qc.invalidateQueries({ queryKey: keys.work(caseId) }),
      qc.invalidateQueries({ queryKey: ["workspace", caseId, "overview"] }),
    ]),
  })
}

export function useWork(
  caseId: string,
  filters: { taskStatus?: TaskStatus | "all"; assigneeUserId?: string } = {},
) {
  return useQuery({
    queryKey: [...keys.work(caseId), filters],
    queryFn: () => workspaceAPI.getWork(caseId, {
      taskStatus: filters.taskStatus,
      assigneeUserId: filters.assigneeUserId,
      limit: 250,
    }),
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
    mutationFn: (context: CaseContextUpdate) =>
      workspaceAPI.updateCaseContext(caseId, context),
    onSuccess: () => Promise.all([
      qc.invalidateQueries({ queryKey: keys.context(caseId) }),
      qc.invalidateQueries({ queryKey: ["workspace", caseId, "overview"] }),
    ]),
  })
}

export function useMandateVersions(caseId: string) {
  return useQuery({
    queryKey: keys.mandates(caseId),
    queryFn: () => workspaceAPI.listMandateVersions(caseId),
  })
}

export function useCreateMandateVersion(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (mandate: MandateVersionCreate) =>
      workspaceAPI.createMandateVersion(caseId, mandate),
    onSuccess: async () => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: keys.context(caseId) }),
        qc.invalidateQueries({ queryKey: keys.mandates(caseId) }),
        qc.invalidateQueries({ queryKey: ["workspace", caseId, "overview"] }),
      ])
    },
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
    onSuccess: () => Promise.all([
      qc.invalidateQueries({ queryKey: keys.pinned(caseId) }),
      qc.invalidateQueries({ queryKey: ["workspace", caseId, "overview"] }),
    ]),
  })
}

export function useBulkPinItems(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (evidenceFileIds: string[]) =>
      workspaceAPI.bulkPinItems(caseId, evidenceFileIds),
    onSuccess: () => Promise.all([
      qc.invalidateQueries({ queryKey: keys.pinned(caseId) }),
      qc.invalidateQueries({ queryKey: ["workspace", caseId, "overview"] }),
    ]),
  })
}

export function usePinStatus(caseId: string, evidenceFileIds: string[]) {
  return useQuery({
    queryKey: [...keys.pinned(caseId), "status", evidenceFileIds],
    queryFn: () => workspaceAPI.getPinStatus(caseId, evidenceFileIds),
    enabled: Boolean(caseId) && evidenceFileIds.length > 0,
  })
}

export function useUnpinItem(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (pinId: string) => workspaceAPI.unpinItem(caseId, pinId),
    onSuccess: () => Promise.all([
      qc.invalidateQueries({ queryKey: keys.pinned(caseId) }),
      qc.invalidateQueries({ queryKey: ["workspace", caseId, "overview"] }),
    ]),
  })
}
