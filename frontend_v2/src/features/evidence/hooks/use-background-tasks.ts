import { useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { backgroundTasksAPI } from "../background-tasks.api"

export function useBackgroundTasks(caseId?: string, polling = false) {
  const queryClient = useQueryClient()
  const completedRef = useRef<Set<string>>(new Set())

  return useQuery({
    queryKey: ["background-tasks", caseId],
    queryFn: async () => {
      const res = await backgroundTasksAPI.list(caseId)
      return res.tasks
    },
    refetchInterval: polling ? 3000 : false,
    select: (tasks) => {
      const terminalStatuses = new Set(["completed", "failed"])
      const currentTerminal = new Set(
        tasks.filter((t) => terminalStatuses.has(t.status)).map((t) => t.id)
      )

      // Detect newly completed/failed tasks
      let hasNew = false
      for (const id of currentTerminal) {
        if (!completedRef.current.has(id)) {
          hasNew = true
          break
        }
      }

      if (hasNew) {
        // Invalidate evidence queries so the file list refreshes
        queryClient.invalidateQueries({ queryKey: ["evidence"] })
      }

      completedRef.current = currentTerminal
      return tasks
    },
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
