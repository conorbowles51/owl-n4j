import { useQueries } from "@tanstack/react-query"
import { useMemo } from "react"
import { fetchAPI } from "@/lib/api-client"
import type { StreamRow } from "./schemas"
import type { UseStream } from "./hooks/use-stream"

/** 05 section 5.4: approach 2's badge per message ("Also on C2", "Only on this phone"), read from the case's latest
 * completed run of Messages across phones. A message the run did not judge has no badge. */
export interface AcrossBadge {
  kind: "both_sides" | "deleted_one_side" | "one_side_only" | "ambiguous_pair"
  other_phone: string | null
  other_record_uid: string | null
  tier: string | null
  words: string
  reasons: string[]
  result_id: string
}
export interface AcrossRun { id: string; finished_at: string | null; current: boolean }
interface AcrossPage { run: AcrossRun | null; items: Record<string, AcrossBadge[]> }

const CHUNK_ROWS = 200
const BATCH = 500

export async function acrossBadges(caseId: string, uids: string[]): Promise<AcrossPage> {
  const out: AcrossPage = { run: null, items: {} }
  for (let i = 0; i < uids.length; i += BATCH) {
    const r = await fetchAPI<AcrossPage>("/api/phone-analysis/across-badges", { method: "POST", body: { case_id: caseId, record_uids: uids.slice(i, i + BATCH) } })
    out.run = r.run
    Object.assign(out.items, r.items)
  }
  return out
}

/** The record uids of each 200-item window of the list whose rows have all arrived; each window is asked once. */
export function loadedChunks(stream: Pick<UseStream, "count" | "item">): string[][] {
  const chunks: string[][] = []
  for (let start = 0; start < stream.count; start += CHUNK_ROWS) {
    const ids: string[] = []
    let complete = true
    for (let i = start; i < Math.min(stream.count, start + CHUNK_ROWS); i++) {
      const it = stream.item(i)
      if (it.type !== "row") continue
      if (!it.row) { complete = false; break }
      ids.push(it.row.record_uid, ...it.row.copies.record_uids)
    }
    if (complete && ids.length) chunks.push(Array.from(new Set(ids)).sort())
  }
  return chunks
}

export function useAcrossBadges(caseId: string | undefined, stream: Pick<UseStream, "count" | "item">) {
  const chunks = useMemo(() => loadedChunks(stream), [stream])
  const qs = useQueries({
    queries: chunks.map((ids) => ({
      queryKey: ["across-badges", caseId, ids.join(",")],
      queryFn: () => acrossBadges(caseId!, ids),
      enabled: !!caseId,
      staleTime: 60_000,
    })),
  })
  const items: Record<string, AcrossBadge[]> = {}
  let run: AcrossRun | null = null
  for (const q of qs) {
    if (!q.data) continue
    run = q.data.run ?? run
    Object.assign(items, q.data.items)
  }
  const forRow = (row: StreamRow): AcrossBadge[] => {
    const seen = new Set<string>()
    const out: AcrossBadge[] = []
    for (const uid of [row.record_uid, ...row.copies.record_uids]) {
      for (const b of items[uid] ?? []) if (!seen.has(b.words)) { seen.add(b.words); out.push(b) }
    }
    return out
  }
  return { run, forRow }
}
