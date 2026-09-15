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
    const requested = params.get("view")
    const view = financialMainViews.includes(requested as FinancialMainView)
      ? (requested as FinancialMainView)
      : "transactions"
    useFinancialStore.getState().setMainView(view)
    return useFinancialStore.subscribe((state, previous) => {
      if (state.mainView === previous.mainView) return
      setParams(
        (current) => {
          const next = new URLSearchParams(current)
          next.set("view", state.mainView)
          return next
        },
        { replace: true }
      )
    })
  }, [caseId, params, setParams])
}
