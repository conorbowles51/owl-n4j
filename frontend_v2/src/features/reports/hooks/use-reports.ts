import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"

export interface Report {
  id: string
  title: string
  description?: string
  format?: string
  content?: string
  sections?: string[]
  created_at?: string
  updated_at?: string
}

interface CreateReportParams {
  title: string
  description?: string
  format: string
  sections: string[]
}

export function useReports(caseId: string | undefined) {
  return useQuery({
    queryKey: ["reports", caseId],
    queryFn: () =>
      fetchAPI<Report[]>(`/api/reports?case_id=${caseId}`),
    enabled: !!caseId,
  })
}

export function useCreateReport(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (params: CreateReportParams) =>
      fetchAPI<Report>("/api/reports", {
        method: "POST",
        body: { ...params, case_id: caseId },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reports", caseId] })
    },
  })
}

export function useDeleteReport(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (reportId: string) =>
      fetchAPI<void>(`/api/reports/${reportId}?case_id=${caseId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reports", caseId] })
    },
  })
}
