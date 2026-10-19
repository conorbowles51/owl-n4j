import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { savedTrails } from "../lib/money-trails"

export function useMoneyTrails(caseId?: string) {
  return useQuery({
    queryKey: ["financial-ledger", caseId, "money-trails"],
    enabled: !!caseId,
    retry: false,
    queryFn: async () => {
      const result = savedTrails.parse(
        await fetchAPI(
          `/api/financial/money-trails?${new URLSearchParams({ case_id: caseId! })}`
        )
      )
      if (result.case_id !== caseId)
        throw Error("The saved trails belong to another case.")
      return result
    },
  })
}
