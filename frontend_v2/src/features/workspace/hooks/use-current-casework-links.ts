import { useMemo } from "react"
import { useQueries, useQueryClient } from "@tanstack/react-query"
import { graphAPI } from "@/features/graph/api"
import { useEvidenceStore } from "@/features/evidence/evidence.store"
import { useGraphStore } from "@/stores/graph.store"
import type { GraphNode, NodeDetail } from "@/types/graph.types"
import { caseworkAPI, type CaseworkLinkInput } from "../casework-api"
import { caseworkKeys } from "./use-casework"
import { usePhoneSelectionStore } from "../stores/phone-selection.store"

/** The attachment-options endpoint names at most this many ids per request; larger selections go in parts. */
export const EVIDENCE_LABEL_PART = 50

export function chunk<T>(items: T[], size: number): T[][] {
  const parts: T[][] = []
  for (let start = 0; start < items.length; start += size) parts.push(items.slice(start, start + size))
  return parts
}

/** Labels for graph nodes already loaded in the case graph, so a large selection does not fetch each node. */
function cachedNodeLabels(queryClient: ReturnType<typeof useQueryClient>, caseId: string) {
  const labels = new Map<string, string>()
  for (const [, data] of queryClient.getQueriesData<{ nodes?: GraphNode[] }>({ queryKey: ["graph", caseId] })) {
    for (const node of data?.nodes ?? []) if (node?.key && node.label) labels.set(node.key, node.label)
  }
  return labels
}

/**
 * Everything the person has selected, as links: graph nodes, evidence files and phone items. Nothing is cut:
 * every selected item is returned, and the count shown beside "Attach selection" is the whole selection.
 */
export function useCurrentCaseworkLinks(caseId: string) {
  const queryClient = useQueryClient()
  const selectedNodeSet = useGraphStore((state) => state.selectedNodeKeys)
  const selectedFileSet = useEvidenceStore((state) => state.selectedFileIds)
  const detailFileId = useEvidenceStore((state) => state.detailFileId)
  const phoneSelection = usePhoneSelectionStore((state) => state.selection)

  const selectedNodeKeys = useMemo(() => Array.from(selectedNodeSet), [selectedNodeSet])
  const selectedFileIds = useMemo(() => {
    const ids = new Set(selectedFileSet)
    if (detailFileId) ids.add(detailFileId)
    return Array.from(ids)
  }, [detailFileId, selectedFileSet])

  const knownLabels = useMemo(
    () => cachedNodeLabels(queryClient, caseId),
    // Recomputed when the selection changes; the graph cache is read, never fetched.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [queryClient, caseId, selectedNodeKeys],
  )
  const unlabelledKeys = useMemo(
    () => selectedNodeKeys.filter((key) => !knownLabels.has(key)),
    [knownLabels, selectedNodeKeys],
  )
  const nodeQueries = useQueries({
    queries: unlabelledKeys.map((key) => ({
      queryKey: ["graph", "node", key, caseId],
      queryFn: () => graphAPI.getNodeDetails(key, caseId),
      staleTime: 30_000,
    })),
  })
  const evidenceParts = useMemo(() => chunk(selectedFileIds, EVIDENCE_LABEL_PART), [selectedFileIds])
  const evidenceQueries = useQueries({
    queries: evidenceParts.map((ids) => ({
      queryKey: caseworkKeys.options(caseId, "evidence", "", ids),
      queryFn: () => caseworkAPI.attachmentOptions(caseId, "evidence", "", ids.length, ids),
      enabled: !!caseId,
      staleTime: 15_000,
    })),
  })

  return useMemo<CaseworkLinkInput[]>(() => {
    const fetchedLabels = new Map<string, string>()
    unlabelledKeys.forEach((key, index) => {
      const detail = nodeQueries[index]?.data as NodeDetail | undefined
      if (detail?.label) fetchedLabels.set(key, detail.label)
    })
    const evidenceById = new Map(
      evidenceQueries.flatMap((query) => query.data?.items ?? []).map((item) => [item.target_id, item]),
    )
    const links: CaseworkLinkInput[] = selectedNodeKeys.map((key) => ({
      target_type: "graph_entity",
      target_id: key,
      target_label: knownLabels.get(key) || fetchedLabels.get(key) || "Selected graph entity",
      relationship: "unclassified",
      source_anchor: {},
      metadata: { source: "current_selection" },
    }))
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
    if (phoneSelection && phoneSelection.caseId === caseId) {
      for (const link of phoneSelection.links) {
        links.push({
          ...link,
          metadata: { ...(link.metadata ?? {}), source: "current_selection", screen: phoneSelection.screen },
        })
      }
    }
    return links
  }, [evidenceQueries, knownLabels, nodeQueries, phoneSelection, caseId, selectedFileIds, selectedNodeKeys, unlabelledKeys])
}
