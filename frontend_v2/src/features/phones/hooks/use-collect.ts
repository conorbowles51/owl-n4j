import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback } from "react"
import { fetchAPI } from "@/lib/api-client"
import type { CollectTarget, TargetKind } from "../collect.api"

/**
 * What Add to… offers (07 section 6.2): the case's dossiers, findings, theories and notes, every one of them (no
 * page cut; a case with more than the request limit is read in parts).
 */
export function useCollectTargets(caseId: string | undefined) {
  return useQuery({
    queryKey: ["collect-targets", caseId],
    enabled: !!caseId,
    staleTime: 30_000,
    queryFn: async (): Promise<CollectTarget[]> => {
      const out: CollectTarget[] = []
      for (let offset = 0; ; offset += 200) {
        const page = await fetchAPI<{ dossiers: { id: string; display_name: string }[]; total: number }>(
          `/api/dossiers?case_id=${encodeURIComponent(caseId!)}&limit=200&offset=${offset}`,
          { read: true },
        )
        out.push(...page.dossiers.map((d) => ({ kind: "dossier" as TargetKind, id: d.id, label: d.display_name })))
        if (offset + 200 >= page.total) break
      }
      const entries = await fetchAPI<{ entries: { id: string; title?: string | null; entry_type: string; tags?: string[] }[] }>(
        `/api/workspace/${encodeURIComponent(caseId!)}/entries`,
        { read: true },
      )
      for (const e of entries.entries) {
        const kind: TargetKind | null = e.tags?.includes("label") ? "label" : e.entry_type === "finding" ? "finding" : e.entry_type === "theory" ? "theory" : e.entry_type === "note" ? "note" : null
        if (kind) out.push({ kind, id: e.id, label: e.title || "(untitled)" })
      }
      return out
    },
  })
}

/** "In 2 dossiers and 1 finding" for each record shown (07 section 6.2), 200 ids per request as the server allows. */
export function useUsedIn(caseId: string | undefined, recordUids: string[]) {
  const qc = useQueryClient()
  const key = ["used-in", caseId, recordUids.slice().sort().join(",")]
  const q = useQuery({
    queryKey: key,
    enabled: !!caseId && recordUids.length > 0,
    staleTime: 10_000,
    queryFn: async () => {
      const out: Record<string, string | null> = {}
      for (let i = 0; i < recordUids.length; i += 200) {
        const part = recordUids.slice(i, i + 200)
        const qs = part.map((id) => `target_ids[]=${encodeURIComponent(id)}`).join("&")
        const r = await fetchAPI<{ results: { target_id: string; summary: string | null }[] }>(
          `/api/workspace/${encodeURIComponent(caseId!)}/collections?target_type=phone_record&${qs}`,
          { read: true },
        )
        for (const x of r.results) out[x.target_id] = x.summary
      }
      return out
    },
  })
  const refresh = useCallback(() => qc.invalidateQueries({ queryKey: ["used-in", caseId] }), [qc, caseId])
  return { usedIn: q.data ?? {}, refresh }
}
