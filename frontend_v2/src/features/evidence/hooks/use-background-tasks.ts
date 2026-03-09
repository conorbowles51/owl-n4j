import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { backgroundTasksAPI } from "../background-tasks.api"

export function useBackgroundTasks(caseId?: string, polling = false) {
  return useQuery({
    queryKey: ["background-tasks", caseId],
    queryFn: async () => {
      const res = await backgroundTasksAPI.list(caseId)
      return res.tasks
    },
    refetchInterval: polling ? 3000 : false,
  })
}

export function useBackgroundTask(taskId: string | undefined) {
  return useQuery({
    queryKey: ["background-task", taskId],
    queryFn: () => backgroundTasksAPI.get(taskId!),
    enabled: !!taskId,
    refetchInterval: 3000,
  })
}

export function useDeleteBackgroundTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (taskId: string) => backgroundTasksAPI.delete(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["background-tasks"] })
    },
  })
}

export function useActiveTaskCount(caseId?: string) {
  const { data: tasks } = useBackgroundTasks(caseId, true)
  return tasks?.filter((t) => t.status === "running" || t.status === "pending").length ?? 0
}
