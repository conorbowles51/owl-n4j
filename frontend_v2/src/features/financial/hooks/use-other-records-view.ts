import { useLayoutEffect } from "react"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { useFinancialStore } from "../stores/financial.store"

type Store = ReturnType<typeof useFinancialStore.getState>
const fields = [
  "searchQuery",
  "startDate",
  "endDate",
  "minAmount",
  "maxAmount",
  "entityFilter",
  "selectedTypes",
  "selectedCategories",
  "sortColumns",
  "pageSize",
  "currentPage",
  "checkedKeys",
  "lastClickedKey",
  "expandedRowKeys",
] as const
function capture(state: Store) {
  return {
    searchQuery: state.searchQuery,
    startDate: state.startDate,
    endDate: state.endDate,
    minAmount: state.minAmount,
    maxAmount: state.maxAmount,
    entityFilter: state.entityFilter,
    selectedTypes: [...state.selectedTypes],
    selectedCategories: [...state.selectedCategories],
    sortColumns: state.sortColumns,
    pageSize: state.pageSize,
    currentPage: state.currentPage,
    checkedKeys: [...state.checkedKeys],
    lastClickedKey: state.lastClickedKey,
    expandedRowKeys: [...state.expandedRowKeys],
  }
}

// The shared controls read this store directly. Hydrate only the current
// member/case view and save changes as browser-tab drafts, not case evidence.
export function useOtherRecordsView(caseId: string | undefined) {
  const owner = useAuthStore(
    (state) => state.user?.id || state.user?.username || "anonymous"
  )
  useLayoutEffect(() => {
    if (!caseId) return
    const key = `${owner}:${caseId}:other-records-view`
    const remembered = useFinancialDraftStore.getState().drafts[key] as
      | ReturnType<typeof capture>
      | undefined
    const defaults = useFinancialStore.getInitialState()
    const current = useFinancialStore.getState()
    const view =
      remembered ??
      capture({
        ...defaults,
        sortColumns: current.sortColumns,
        pageSize: current.pageSize,
      })
    useFinancialStore.setState({
      ...view,
      selectedTypes: new Set(view.selectedTypes),
      selectedCategories: new Set(view.selectedCategories),
      checkedKeys: new Set(view.checkedKeys),
      expandedRowKeys: new Set(view.expandedRowKeys),
    })
    return useFinancialStore.subscribe((state, previous) => {
      if (fields.some((field) => state[field] !== previous[field])) {
        useFinancialDraftStore.getState().put(key, capture(state))
      }
    })
  }, [caseId, owner])
}
