import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { readDuplicateCandidates } from "../lib/duplicate-format"

export function useDuplicateCandidates(
  caseId: string | undefined,
  enabled: boolean
) {
  return useQuery({
    // Ledger mutations invalidate the comparison's row counts and membership.
    queryKey: ["financial-ledger", caseId, "duplicates"],
    queryFn: async () => {
      if (!caseId) throw new Error("Choose a case to compare documents.")
      return readDuplicateCandidates(
        await fetchAPI<unknown>(
          `/api/financial/duplicates?${new URLSearchParams({ case_id: caseId })}`
        ),
        caseId
      )
    },
    enabled: !!caseId && enabled,
    retry: false,
  })
}
