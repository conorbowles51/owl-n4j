import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"

const response = z.object({
  case_id: z.string(),
  total: z.number().int().nonnegative(),
  entries: z.array(
    z.object({
      id: z.string(),
      title: z.string().nullable(),
      tags: z.array(z.string()),
      payment_ids: z.array(z.string()),
    })
  ),
})
export function useFinancialFindingIndex(caseId: string | undefined) {
  return useQuery({
    queryKey: ["casework", caseId, "financial-payment-links"],
    enabled: !!caseId,
    retry: false,
    queryFn: async ({ signal }) => {
      const entries: z.infer<typeof response>["entries"] = []
      let total: number | undefined
      do {
        const page = response.parse(
          await fetchAPI(
            `/api/workspace/${encodeURIComponent(caseId!)}/financial-payment-links?limit=200&offset=${entries.length}`,
            { signal }
          )
        )
        if (
          page.case_id !== caseId ||
          (total !== undefined && total !== page.total) ||
          (!page.entries.length && entries.length < page.total)
        )
          throw Error(
            "Saved findings changed while loading. Refresh to check every link."
          )
        total = page.total
        entries.push(...page.entries)
      } while (entries.length < total)
      if (
        entries.length !== total ||
        new Set(entries.map((entry) => entry.id)).size !== entries.length
      )
        throw Error(
          "Not all finding links were returned. Refresh to check them."
        )
      return entries.filter((entry) => !entry.tags.includes("financial-report"))
    },
  })
}
