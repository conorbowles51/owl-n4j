import { useQuery } from "@tanstack/react-query"
import { financialAPI } from "../api"
import { readProofStanding } from "../lib/proof-standing-format"

/** Whole-case census: no graph filters, no previous case's placeholder, no writes. */
export function useProofStanding(caseId: string | undefined) {
  return useQuery({
    queryKey: ["financial-proof-standing", caseId],
    queryFn: async () => {
      if (!caseId)
        throw new Error("Choose a case to read its evidence classification.")
      return readProofStanding(
        await financialAPI.getCaseProofStanding(caseId),
        caseId
      )
    },
    enabled: !!caseId,
  })
}
