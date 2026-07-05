import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { timelineAPI, type TimelineViewInput, type TimelineViewUpdate } from "../api"

export const timelineViewKeys = {
  all: (caseId: string | undefined) => ["timeline-views", caseId] as const,
  list: (caseId: string | undefined) => ["timeline-views", caseId, "list"] as const,
  detail: (caseId: string | undefined, viewId: string | null | undefined) =>
    ["timeline-views", caseId, "detail", viewId] as const,
}

export function useTimelineViews(caseId: string | undefined) {
  return useQuery({
    queryKey: timelineViewKeys.list(caseId),
    queryFn: () => timelineAPI.listViews(caseId!),
    enabled: !!caseId,
  })
}

export function useTimelineView(
  caseId: string | undefined,
  viewId: string | null | undefined
) {
  return useQuery({
    queryKey: timelineViewKeys.detail(caseId, viewId),
    queryFn: () => timelineAPI.getView(caseId!, viewId!),
    enabled: !!caseId && !!viewId,
  })
}

export function useCreateTimelineView() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: TimelineViewInput) => timelineAPI.createView(input),
    onSuccess: (view) => {
      queryClient.invalidateQueries({ queryKey: timelineViewKeys.all(view.case_id) })
    },
  })
}

export function useUpdateTimelineView(caseId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ viewId, input }: { viewId: string; input: TimelineViewUpdate }) =>
      timelineAPI.updateView(viewId, input),
    onSuccess: (view) => {
      queryClient.invalidateQueries({ queryKey: timelineViewKeys.all(view.case_id) })
    },
    onSettled: () => {
      if (caseId) queryClient.invalidateQueries({ queryKey: timelineViewKeys.all(caseId) })
    },
  })
}

export function useDeleteTimelineView(caseId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (viewId: string) => timelineAPI.deleteView(caseId!, viewId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: timelineViewKeys.all(caseId) })
    },
  })
}

export function useUpdateTimelineViewEvents(caseId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      viewId,
      action,
      eventKeys,
    }: {
      viewId: string
      action: "add" | "remove" | "set"
      eventKeys: string[]
    }) => timelineAPI.updateViewEvents(caseId!, viewId, action, eventKeys),
    onSuccess: (view) => {
      queryClient.invalidateQueries({ queryKey: timelineViewKeys.all(view.case_id) })
    },
  })
}
