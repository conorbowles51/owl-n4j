import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useState } from "react"
import { fetchAPI } from "@/lib/api-client"
import type { CollectTarget, TargetKind } from "../collect.api"

/**
 * What Add to… offers (07 section 6.2): the case's dossiers, findings, theories and notes, every one of them (no
 * page cut; a case with more than the request limit is read in parts).
 */
export function useCollectTargets(caseId: string | undefined) {
  return useQuery({ ...collectTargetsQuery(caseId), enabled: !!caseId, staleTime: 30_000 })
}

/** Key and fetcher shared by the hook and the start-up prefetch (route-data.ts). */
export function collectTargetsQuery(caseId: string | undefined) {
  return {
    queryKey: ["collect-targets", caseId],
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
  }
}

/** How long rows that are still loading may keep changing before their marks are asked for anyway (a window that
 * never arrives must not hold back the marks of the rows that did). */
export const USED_IN_WAIT_MS = 1500

/** "In 2 dossiers and 1 finding" for each record shown (07 section 6.2), 200 ids per request as the server allows.
 * Asked once the shown rows are all loaded (``complete``), so one load of a list makes one request however many
 * windows it arrives in; while rows are still loading, asked only if they stop changing for USED_IN_WAIT_MS. */
export function useUsedIn(caseId: string | undefined, recordUids: string[], complete = true) {
  const qc = useQueryClient()
  const joined = recordUids.slice().sort().join(",")
  const [settled, setSettled] = useState(complete ? joined : "")
  useEffect(() => {
    if (joined === settled) return
    const t = setTimeout(() => setSettled(joined), complete ? 0 : USED_IN_WAIT_MS)
    return () => clearTimeout(t)
  }, [joined, settled, complete])
  const ids = settled ? settled.split(",") : []
  const key = ["used-in", caseId, settled]
  const q = useQuery({
    queryKey: key,
    enabled: !!caseId && ids.length > 0,
    staleTime: 10_000,
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const out: Record<string, string | null> = {}
      for (let i = 0; i < ids.length; i += 200) {
        const part = ids.slice(i, i + 200)
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
