import { useQuery } from "@tanstack/react-query"
import { useMemo } from "react"
import { phonesQuery } from "../phones-query"

export interface LayerPhone { id: string; label: string; index: number }

/** Every active phone of the case; its index is its place in the case's list (the order PhoneChip's colour uses). A replaced report is not a layer. */
export function useCasePhones(caseId: string): LayerPhone[] {
  const q = useQuery({ ...phonesQuery(caseId), enabled: !!caseId })
  return useMemo(() => (q.data?.phones ?? []).map((p, index) => ({ p, index })).filter(({ p }) => p.standing !== "superseded").map(({ p, index }) => ({ id: p.extraction_id, label: p.label, index })), [q.data])
}
