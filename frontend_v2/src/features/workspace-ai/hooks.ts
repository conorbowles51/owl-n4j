import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  workspaceAIAPI,
  type WorkspaceAIOutput,
  type WorkspaceAITargetType,
} from "./api"

export const workspaceAIKeys = {
  target: (
    caseId: string,
    targetType: WorkspaceAITargetType,
    targetId: string,
  ) => ["workspace-ai", caseId, targetType, targetId] as const,
}

export function useWorkspaceAIOutputs(
  caseId: string,
  targetType: WorkspaceAITargetType,
  targetId: string,
) {
  return useQuery({
    queryKey: workspaceAIKeys.target(caseId, targetType, targetId),
    queryFn: () => workspaceAIAPI.list(caseId, targetType, targetId),
    enabled: Boolean(caseId && targetId),
    refetchInterval: (query) => {
      const data = query.state.data
      return data?.outputs.some((item) =>
        ["queued", "running"].includes(item.job_status),
      )
        ? 1_000
        : false
    },
  })
}

export function useWorkspaceAIMutation(
  caseId: string,
  targetType: WorkspaceAITargetType,
  targetId: string,
  mutation: () => Promise<WorkspaceAIOutput>,
) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: mutation,
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({
          queryKey: workspaceAIKeys.target(caseId, targetType, targetId),
        }),
        client.invalidateQueries({ queryKey: ["dossiers", "detail", targetId] }),
        client.invalidateQueries({ queryKey: ["casework", caseId] }),
        client.invalidateQueries({ queryKey: ["workspace", caseId, "overview"] }),
      ])
    },
  })
}
