import {
  financialDraftKey,
  useFinancialDraftStore,
} from "../stores/financial-drafts"
import { useLayoutEffect } from "react"
import { useSearchParams } from "react-router-dom"
import {
  financialMainViews,
  type FinancialMainView,
  useFinancialStore,
} from "../stores/financial.store"

// Keep navigation in the URL so refresh and browser Back restore the actual
// tab. Subscribe while this page is mounted so file-list actions use it too.
export function useFinancialViewNavigation(caseId: string | undefined) {
  const [params, setParams] = useSearchParams()
  useLayoutEffect(() => {
    if (!caseId) return
    const requested =
      params.get("view") ||
      (useFinancialDraftStore.getState().drafts[
        financialDraftKey(caseId, "last-view")
      ] as string | undefined)
    const view = financialMainViews.includes(requested as FinancialMainView)
      ? (requested as FinancialMainView)
      : "overview"
    useFinancialStore.getState().setMainView(view)
    const mode =
      params.get("dataset") === "other-records"
        ? "intelligence"
        : "transactions"
    if (useFinancialStore.getState().mode !== mode)
      useFinancialStore.getState().setMode(mode)
    return useFinancialStore.subscribe((state, previous) => {
      if (state.mainView === previous.mainView && state.mode === previous.mode)
        return
      useFinancialDraftStore
        .getState()
        .put(financialDraftKey(caseId, "last-view"), state.mainView)
      setParams(
        (current) => {
          const next = new URLSearchParams(current)
          next.set("view", state.mainView)
          if (state.mode === "intelligence")
            next.set("dataset", "other-records")
          else next.delete("dataset")
          return next
        },
        { replace: true }
      )
    })
  }, [caseId, params, setParams])
}
