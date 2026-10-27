import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { useFinancialDraft } from "../stores/financial-drafts"

export const categoryName = (row: { category?: string }) =>
  row.category || "Uncategorized"

/** Older drafts and links hold one category as a string; newer ones a list. */
export const categoryList = (value: unknown): string[] =>
  Array.isArray(value)
    ? [...new Set(value.filter((v): v is string => typeof v === "string" && !!v))]
    : typeof value === "string" && value
      ? [value]
      : []

export const matchesCategories = (
  row: { category?: string },
  categories: string[]
) => !categories.length || categories.includes(categoryName(row))

const ALL_CATEGORIES: string[] = []

/** The categories chosen across financial views: empty means all. */
export function usePaymentCategory(caseId: string) {
  const [raw, setRaw] = useFinancialDraft<string | string[]>(
    caseId,
    "investigation-category",
    ALL_CATEGORIES
  )
  const categories = useMemo(() => categoryList(raw), [raw])
  const setCategories = (next: string | string[]) =>
    setRaw(categoryList(next))
  return [categories, setCategories] as const
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
