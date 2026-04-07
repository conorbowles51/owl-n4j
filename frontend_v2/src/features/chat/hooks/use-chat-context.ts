import { useMemo } from "react"
import { useQueries } from "@tanstack/react-query"
import { useGraphStore } from "@/stores/graph.store"
import { graphAPI } from "@/features/graph/api"
import { useEvidenceStore } from "@/features/evidence/evidence.store"
import { useEvidence } from "@/features/evidence/hooks/use-evidence"
import type { ContextNode } from "../types"

export function useChatContext(caseId: string) {
  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)
  const selectedFileIds = useEvidenceStore((s) => s.selectedFileIds)
  const detailFileId = useEvidenceStore((s) => s.detailFileId)
  const { data: evidenceFiles = [] } = useEvidence(caseId)

  const selectedKeyArray = useMemo(
    () => Array.from(selectedNodeKeys),
    [selectedNodeKeys]
  )

  const selectedNodeQueries = useQueries({
    queries: selectedKeyArray.map((key) => ({
      queryKey: ["graph-node-detail", caseId, key],
      queryFn: () => graphAPI.getNodeDetails(key, caseId),
      enabled: !!caseId,
      staleTime: 60_000,
    })),
  })

  const selectedNodes = useMemo<ContextNode[]>(() => {
    return selectedNodeQueries
      .map((query, index) => {
        const data = query.data
        const key = selectedKeyArray[index]
        if (!key) return null
        if (!data) {
          return {
            key,
            label: key,
            type: "unknown" as ContextNode["type"],
          }
        }
        return {
          key,
          label: String(data.label || data.key || key),
          type: String(data.type || "unknown") as ContextNode["type"],
        }
      })
      .filter((item): item is ContextNode => item !== null)
  }, [selectedKeyArray, selectedNodeQueries])

  const scopedDocument = useMemo<string | null>(() => {
    const selectedIds = Array.from(selectedFileIds)
    const fileLookup = new Map(
      evidenceFiles.map((file) => [
        file.id,
        file.original_filename,
      ])
    )

    if (detailFileId && fileLookup.has(detailFileId)) {
      return fileLookup.get(detailFileId) ?? null
    }

    if (selectedIds.length === 1) {
      return fileLookup.get(selectedIds[0]) ?? "1 selected evidence file"
    }

    if (selectedIds.length > 1) {
      return `${selectedIds.length} selected evidence files`
    }

    return null
  }, [detailFileId, evidenceFiles, selectedFileIds])

  return {
    selectedNodes,
    scopedDocument,
    selectedNodeKeys: selectedKeyArray,
  }
}
