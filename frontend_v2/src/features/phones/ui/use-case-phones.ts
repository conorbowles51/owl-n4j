import { useQuery } from "@tanstack/react-query"
import { useMemo } from "react"
import { phonesQuery } from "../phones-query"

export interface LayerPhone { id: string; label: string; index: number }

/** Every phone of the case in the case's stable order (the order PhoneChip's colour index uses). */
export function useCasePhones(caseId: string): LayerPhone[] {
  const q = useQuery({ ...phonesQuery(caseId), enabled: !!caseId })
  return useMemo(() => (q.data?.phones ?? []).map((p, index) => ({ id: p.extraction_id, label: p.label, index })), [q.data])
}
