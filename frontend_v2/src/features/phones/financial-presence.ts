import { useQuery } from "@tanstack/react-query"
import { getFinancialPresence } from "./api"

/** 07 section 8: whether the case holds financial evidence. Money parts beside the phones show `phone_sentence`
 * when it does not, never "0 payments"; the Financial page shows `financial_sentence`. */
export function useFinancialPresence(caseId: string | undefined) {
  return useQuery({
    queryKey: ["financial-presence", caseId],
    queryFn: () => getFinancialPresence(caseId!),
    enabled: !!caseId,
    staleTime: 60_000,
    retry: false,
  })
}
