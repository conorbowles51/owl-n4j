import { useQuery, useQueryClient } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import type { FinancialCategory } from "../api"

export function usePaymentCategoryLibrary(caseId: string) {
  return useQuery({
    queryKey: ["financial-category-library", caseId],
    queryFn: async () => {
      const result = await fetchAPI<{
        case_id: string
        categories: (FinancialCategory & { scope?: string })[]
      }>(
        `/api/financial/ledger/category-library?${new URLSearchParams({ case_id: caseId })}`
      )
      if (result.case_id !== caseId)
        throw Error("Categories came from a different case.")
      return result.categories
    },
  })
}

export function useCreatePaymentCategory(caseId: string) {
  const client = useQueryClient()
  return async (name: string, color: string) => {
    const result = await fetchAPI<{
      case_id: string
      category: FinancialCategory
    }>(
      `/api/financial/ledger/category-library?${new URLSearchParams({ case_id: caseId })}`,
      { method: "POST", body: { name, color } }
    )
    if (result.case_id !== caseId || !result.category?.name)
      throw Error(
        "The saved category was not confirmed. Reload categories before trying again."
      )
    await client.invalidateQueries({ queryKey: ["financial-category-library"] })
    return result.category
  }
}
