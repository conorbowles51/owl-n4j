import type { NodeDetail } from "@/types/graph.types"
import type { NotebookLinkInput } from "../api"

interface EvidenceLabel {
  id: string
  original_filename?: string | null
}

export function buildNotebookContextLinks({
  selectedNodeKeys,
  selectedNodeDetails,
  selectedFileIds,
  evidenceFiles,
}: {
  selectedNodeKeys: string[]
  selectedNodeDetails: Array<NodeDetail | undefined>
  selectedFileIds: string[]
  evidenceFiles: EvidenceLabel[]
}): NotebookLinkInput[] {
  const evidenceById = new Map(evidenceFiles.map((file) => [file.id, file]))
  const links: NotebookLinkInput[] = []

  selectedNodeKeys.forEach((key, index) => {
    links.push({
      target_type: "entity",
      target_id: key,
      target_label: selectedNodeDetails[index]?.label || key,
      metadata: { source: "current_selection" },
    })
  })

  selectedFileIds.forEach((id) => {
    links.push({
      target_type: "evidence",
      target_id: id,
      target_label: evidenceById.get(id)?.original_filename || id,
      metadata: { source: "current_selection" },
    })
  })

  return links
}
