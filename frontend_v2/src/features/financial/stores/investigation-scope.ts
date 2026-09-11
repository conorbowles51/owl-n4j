import { create } from "zustand"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"

type Scope = Pick<LedgerQueryParams, "accountId" | "startDate" | "endDate">
const emptyScope: Scope = {}

// A case's applied account/date selection follows its investigation tabs.
// Draft filter edits stay in the form until Apply. Nothing is written to disk.
export const useInvestigationScopeStore = create<{
  scopes: Record<string, Scope>
  apply: (caseId: string, scope: Scope) => void
  reset: () => void
}>((set) => ({
  scopes: {},
  apply: (caseId, scope) =>
    set((state) => ({
      scopes: {
        ...state.scopes,
        [caseId]: {
          accountId: scope.accountId,
          startDate: scope.startDate,
          endDate: scope.endDate,
        },
      },
    })),
  reset: () => {
    set({ scopes: {} })
    useAnalysisPopulationStore.setState({ cases: {} })
  },
}))

export function useInvestigationScope(caseId: string | undefined) {
  const scope = useInvestigationScopeStore((state) =>
    caseId ? (state.scopes[caseId] ?? emptyScope) : emptyScope
  )
  const apply = useInvestigationScopeStore((state) => state.apply)
  return [
    scope,
    (value: Scope) => {
      if (caseId) apply(caseId, value)
    },
  ] as const
}

export type AnalysisPopulation = "working" | "verified"
const useAnalysisPopulationStore = create<{
  cases: Record<string, AnalysisPopulation>
  set: (caseId: string, value: AnalysisPopulation) => void
}>((set) => ({
  cases: {},
  set: (caseId, value) =>
    set((state) => ({ cases: { ...state.cases, [caseId]: value } })),
}))

export function useAnalysisPopulation(caseId: string | undefined) {
  const population = useAnalysisPopulationStore((state) =>
    caseId ? (state.cases[caseId] ?? "working") : "working"
  )
  const set = useAnalysisPopulationStore((state) => state.set)
  return [
    population,
    (value: string) => {
      if (caseId && (value === "working" || value === "verified"))
        set(caseId, value)
    },
  ] as const
}
