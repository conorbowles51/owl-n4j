import { useMemo } from "react"
import { useQueries } from "@tanstack/react-query"
import { graphAPI } from "@/features/graph/api"
import { useEvidenceStore } from "@/features/evidence/evidence.store"
import { useGraphStore } from "@/stores/graph.store"
import type { NodeDetail } from "@/types/graph.types"
import type { CaseworkLinkInput } from "../casework-api"
import { useAttachmentOptions } from "./use-casework"

export function useCurrentCaseworkLinks(caseId: string) {
  const selectedNodeSet = useGraphStore((state) => state.selectedNodeKeys)
  const selectedFileSet = useEvidenceStore((state) => state.selectedFileIds)
  const detailFileId = useEvidenceStore((state) => state.detailFileId)

  const selectedNodeKeys = useMemo(
    () => Array.from(selectedNodeSet).slice(0, 6),
    [selectedNodeSet],
  )
  const selectedFileIds = useMemo(() => {
    const ids = new Set(Array.from(selectedFileSet).slice(0, 6))
    if (detailFileId) ids.add(detailFileId)
    return Array.from(ids).slice(0, 6)
  }, [detailFileId, selectedFileSet])

  const nodeQueries = useQueries({
    queries: selectedNodeKeys.map((key) => ({
      queryKey: ["graph", "node", key, caseId],
      queryFn: () => graphAPI.getNodeDetails(key, caseId),
      staleTime: 30_000,
    })),
  })
  const evidenceQuery = useAttachmentOptions(
    caseId,
    "evidence",
    "",
    selectedFileIds.length > 0,
    selectedFileIds,
  )

  return useMemo<CaseworkLinkInput[]>(() => {
    const evidenceById = new Map(
      (evidenceQuery.data?.items ?? []).map((item) => [item.target_id, item]),
    )
    const links: CaseworkLinkInput[] = selectedNodeKeys.map((key, index) => {
      const detail = nodeQueries[index]?.data as NodeDetail | undefined
      return {
        target_type: "graph_entity",
        target_id: key,
        target_label: detail?.label || "Selected graph entity",
        relationship: "unclassified",
        source_anchor: {},
        metadata: { source: "current_selection" },
      }
    })
    for (const id of selectedFileIds) {
      const option = evidenceById.get(id)
      links.push({
        target_type: "evidence",
        target_id: id,
        target_label: option?.label || "Selected evidence",
        relationship: "unclassified",
        source_anchor: {},
        metadata: { ...(option?.metadata ?? {}), source: "current_selection" },
      })
    }
    return links
  }, [evidenceQuery.data?.items, nodeQueries, selectedFileIds, selectedNodeKeys])
}
