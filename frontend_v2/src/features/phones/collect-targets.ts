import { useQuery } from "@tanstack/react-query"
import { dossiersAPI } from "@/features/dossiers/api"
import { caseworkAPI } from "@/features/workspace/casework-api"
import type { CollectTarget } from "./collect.api"

/**
 * The places a phone item can be added to (07 section 6.2): the case's dossiers and its Workspace findings,
 * theories and notes, for AddToMenu. Shared by every phone screen. Each list is read up to TARGET_LIMIT, most
 * recently changed first; when a case has more, `note` says how many are not offered so nothing is cut silently.
 */
export const TARGET_LIMIT = 200

export interface CollectTargets {
  targets: CollectTarget[]
  note: string | null
  loading: boolean
  error: unknown
}

export function targetsNote(dossiers: { shown: number; total: number }, entries: { shown: number; total: number }): string | null {
  const parts: string[] = []
  if (dossiers.total > dossiers.shown) parts.push(`${dossiers.shown.toLocaleString("en-US")} of ${dossiers.total.toLocaleString("en-US")} dossiers`)
  if (entries.total > entries.shown) parts.push(`${entries.shown.toLocaleString("en-US")} of ${entries.total.toLocaleString("en-US")} findings, theories and notes`)
  return parts.length ? `Offering the most recently changed ${parts.join(" and ")}. Add from the dossier or Workspace for the others.` : null
}

export function useCollectTargets(caseId: string): CollectTargets {
  const dossiers = useQuery({
    queryKey: ["collect-targets", "dossiers", caseId],
    queryFn: () => dossiersAPI.list({ caseId, limit: TARGET_LIMIT }),
    enabled: !!caseId,
  })
  const entries = useQuery({
    queryKey: ["collect-targets", "entries", caseId],
    queryFn: () => caseworkAPI.list(caseId, { sort_by: "updated_at", sort_direction: "desc", limit: TARGET_LIMIT }),
    enabled: !!caseId,
  })
  const targets: CollectTarget[] = [
    ...(dossiers.data?.dossiers || []).map((d) => ({ kind: "dossier" as const, id: d.id, label: d.display_name || d.display_name_snapshot })),
    ...(entries.data?.entries || []).map((e) => ({ kind: e.entry_type, id: e.id, label: e.title || "Untitled" })),
  ]
  const note = dossiers.data && entries.data
    ? targetsNote({ shown: dossiers.data.dossiers.length, total: dossiers.data.total }, { shown: entries.data.entries.length, total: entries.data.total })
    : null
  return { targets, note, loading: dossiers.isLoading || entries.isLoading, error: dossiers.error || entries.error }
}
