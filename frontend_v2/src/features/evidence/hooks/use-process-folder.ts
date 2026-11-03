import { useMutation, useQueryClient } from "@tanstack/react-query"
import { transcriptsAPI } from '../transcripts.api'
import type { ProcessGate } from './use-guarded-process'

export function useProcessFolder(caseId: string, gate: ProcessGate) {
  const qc = useQueryClient()
  const mutation = useMutation({
    mutationFn: async (data: {
      folderId: string
      recursive?: boolean
      reprocessCompleted?: boolean
    }) => {
      const plan = await transcriptsAPI.plan({ case_id: caseId, folder_id: data.folderId,
        recursive: data.recursive ?? true, reprocess_completed: data.reprocessCompleted ?? false })
      const ids: string[] = []
      let cursor: number | null = 0
      while (cursor !== null) {
        const page = await transcriptsAPI.files(plan.id, cursor)
        ids.push(...page.items.filter(item => !item.skipped).map(item => item.id))
        cursor = page.next_cursor
      }
      const result = await gate.start({ fileIds: ids, reprocessCompleted: data.reprocessCompleted })
      return { file_count: ids.length, held: result !== 'started', message: result === 'started' ? `Processing ${ids.length} files` : 'Review processing choices' }
    },
    onSuccess: async () => {
      qc.invalidateQueries({ queryKey: ["evidence-jobs", caseId] })
      qc.invalidateQueries({ queryKey: ["evidence-folder-contents", caseId] })
      qc.invalidateQueries({ queryKey: ["evidence-folder-tree", caseId] })
      qc.invalidateQueries({ queryKey: ["evidence", caseId] })
      await qc.refetchQueries({ queryKey: ["evidence-jobs", caseId], type: "active" })
    },
  })
  return { ...mutation, gate }
}
