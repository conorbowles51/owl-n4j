import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { useFinancialDraft } from "../stores/financial-drafts"

export const categoryName = (row: { category?: string }) =>
  row.category || "Uncategorized"
export function usePaymentCategory(caseId: string) {
  return useFinancialDraft(caseId, "investigation-category", "")
}
export function usePaymentCategories(caseId: string) {
  return useQuery({
    queryKey: ["financial-ledger", caseId, "categories"],
    queryFn: async () => {
      const result = await fetchAPI<{ case_id: string; categories: string[] }>(
        `/api/financial/ledger-categories?${new URLSearchParams({ case_id: caseId })}`
      )
      if (result.case_id !== caseId)
        throw Error("Categories came from a different case.")
      return result.categories
    },
    enabled: caseId !== "none",
  })
}
