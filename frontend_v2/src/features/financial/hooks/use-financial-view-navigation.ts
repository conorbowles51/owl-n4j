import {
  financialDraftKey,
  useFinancialDraftStore,
} from "../stores/financial-drafts"
import { useEffect, useLayoutEffect } from "react"
import { useSearchParams } from "react-router-dom"
import { showAllImportedPayments } from "../lib/payment-table-draft"
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
    // A fresh visit to Financial uses the full case. Explicit statement/batch
    // navigation and browser Back retain their intentionally selected scope.
    if (!params.get("view") && view === "transactions")
      showAllImportedPayments(caseId)
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
        { replace: state.mainView === previous.mainView }
      )
    })
  }, [caseId, params, setParams])
  useEffect(() => {
    if (!caseId || params.get("view")) return
    // Normalize after the router is mounted. Back must restore this initial
    // entry rather than reuse the destination saved as last-view.
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        next.set("view", useFinancialStore.getState().mainView)
        return next
      },
      { replace: true }
    )
  }, [caseId, params, setParams])
}
