import { useNavigate } from "react-router-dom"
import { paymentPath } from "@/lib/citations"
import { useGraphStore } from "@/stores/graph.store"
import { useTimelineStore } from "@/features/timeline/stores/timeline.store"
import { financialDraftKey, useFinancialDraftStore } from "@/features/financial/stores/financial-drafts"
import type { Member } from "./api"

/**
 * Where an addition came from, to open it there (lx-theorybuild C): a ledger row in the ledger, a file in Evidence,
 * a quote in its file's text, a phone record, a workspace entry, a timeline event, an agent answer's chat. Graph and
 * map selections and timeline ranges have no address of their own: they are opened by setting the page's own state
 * (the graph's workspace source, the selected keys, the timeline's date range) and going there.
 */
const c = (caseId: string) => `/cases/${encodeURIComponent(caseId)}`

export function memberHref(caseId: string, type: string, id: string, anchor: Record<string, unknown>): string | null {
  switch (type) {
    case "financial_transaction":
      return paymentPath(caseId, id)
    case "evidence":
      return `${c(caseId)}/evidence?file=${encodeURIComponent(id)}`
    case "evidence_passage": {
      const fileId = String(anchor.evidence_file_id || id.split(":")[0] || "")
      if (!fileId) return null
      const start = anchor.start_char !== undefined ? `?start_char=${encodeURIComponent(String(anchor.start_char))}` : ""
      return `${c(caseId)}/evidence/${encodeURIComponent(fileId)}/text${start}`
    }
    case "phone_record":
      return `${c(caseId)}/records/${encodeURIComponent(id)}`
    case "entry":
      return `${c(caseId)}/workspace?entry=${encodeURIComponent(id)}`
    case "timeline_event":
      return `${c(caseId)}/timeline?event=${encodeURIComponent(id)}`
    case "dossier":
      return `${c(caseId)}/dossiers?dossier=${encodeURIComponent(id)}`
    case "agent_answer":
    case "agent_artifact":
      return `${c(caseId)}/agent`
    default:
      return null
  }
}

export function theoryHref(caseId: string, entryId: string): string {
  return `${c(caseId)}/workspace?entry=${encodeURIComponent(entryId)}`
}

export interface OpenTarget {
  label: string
  linkId: string
  /** The group's link type, or the single item's. */
  targetType: string
  how?: Record<string, unknown> | null
  members: Pick<Member, "type" | "id">[]
}

/** Opens a group (or single graph item) on the page it came from, in that page's own terms. */
export function useOpenGroup(caseId: string) {
  const navigate = useNavigate()
  return (t: OpenTarget) => {
    const keys = t.members.filter((m) => m.type === "graph_entity").map((m) => m.id)
    const rows = t.members.filter((m) => m.type === "financial_transaction").map((m) => m.id)
    if (t.targetType === "map_selection") {
      useGraphStore.getState().selectNodes(keys)
      navigate(`${c(caseId)}/map`)
      return
    }
    if (t.targetType === "timeline_range") {
      const range = (t.how?.range ?? {}) as { start?: string | null; end?: string | null }
      useTimelineStore.getState().setDateRange({ start: range.start ?? null, end: range.end ?? null })
      navigate(`${c(caseId)}/timeline`)
      return
    }
    if (t.targetType === "financial_selection" && rows.length) {
      // The ledger opens with exactly these rows selected; how they were chosen is shown in the Loupe.
      useFinancialDraftStore.getState().put(financialDraftKey(caseId, "selected-payments"), rows)
      navigate(rows.length === 1 ? paymentPath(caseId, rows[0]) : `${c(caseId)}/financial?view=transactions`)
      return
    }
    if (t.targetType === "evidence_selection") {
      const first = t.members.find((m) => m.type === "evidence")
      navigate(first ? memberHref(caseId, "evidence", first.id, {})! : `${c(caseId)}/evidence`)
      return
    }
    if (keys.length) {
      navigate(`${c(caseId)}/graph`, {
        state: { workspaceGraphSource: { sourceType: "theory_addition", sourceId: t.linkId, sourceLabel: t.label, entityKeys: keys } },
      })
    }
  }
}

/** Whether useOpenGroup can open this kind of addition. */
export function opensAsGroup(targetType: string): boolean {
  return ["graph_selection", "significant_set", "map_selection", "timeline_range", "financial_selection", "evidence_selection", "graph_entity"].includes(targetType)
}
