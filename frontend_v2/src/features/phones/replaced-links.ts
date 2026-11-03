import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"

/** 07 CO-9a and CO-9b: whether a linked phone record is on a replaced report, and the record with the equal key in
 * the report that replaced it. */
export interface ReplacedState {
  replaced: boolean
  words: string | null
  newer_extraction_id: string | null
  newer_record_uid: string | null
  newer_record_type: string | null
}

const BATCH = 500

export async function replacedLinks(caseId: string, uids: string[]): Promise<Record<string, ReplacedState>> {
  const out: Record<string, ReplacedState> = {}
  for (let i = 0; i < uids.length; i += BATCH) {
    const r = await fetchAPI<{ items: Record<string, ReplacedState> }>("/api/phones/records/replacements",
      { method: "POST", body: { case_id: caseId, record_uids: uids.slice(i, i + BATCH) } })
    Object.assign(out, r.items)
  }
  return out
}

/** The state of every phone record link among ``links``, asked once per entry or dossier. */
export function useReplacedLinks(caseId: string, links: { target_type: string; target_id: string }[] | undefined) {
  const uids = Array.from(new Set((links ?? []).filter((l) => l.target_type === "phone_record").map((l) => l.target_id))).sort()
  const q = useQuery({ queryKey: ["phone-replaced-links", caseId, uids], queryFn: () => replacedLinks(caseId, uids), enabled: !!caseId && uids.length > 0 })
  return q.data ?? {}
}
