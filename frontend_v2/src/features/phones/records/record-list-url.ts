import type { RecordListFilter } from "../api"

/** The list for a record type keeps its filters in the address, so a Summary count opens exactly what it counts. */
export function recordListFilter(search: string): RecordListFilter {
  const q = new URLSearchParams(search)
  const one = <T extends string>(name: string, allowed: readonly T[]) => {
    const v = q.get(name) as T | null
    return v && allowed.includes(v) ? v : undefined
  }
  return {
    placement: one("placement", ["all", "top", "nested"] as const),
    deleted: one("deleted", ["any", "only", "hide"] as const),
    copies: one("copies", ["any", "only", "hide"] as const),
    from: q.get("from") ?? undefined,
    to: q.get("to") ?? undefined,
    sort: one("sort", ["time", "report", "title", "deleted"] as const),
    direction: one("direction", ["asc", "desc"] as const),
  }
}

/** The address of a list; the Summary builds every count's link here. */
export function recordListHref(caseId: string, extraction: string, modelType: string, filter: { placement?: "top" | "nested"; deleted?: "only"; copies?: "only" } = {}) {
  const q = new URLSearchParams(filter)
  const tail = q.size ? `?${q}` : ""
  return `/cases/${encodeURIComponent(caseId)}/phones/${encodeURIComponent(extraction)}/records/${encodeURIComponent(modelType)}${tail}`
}
