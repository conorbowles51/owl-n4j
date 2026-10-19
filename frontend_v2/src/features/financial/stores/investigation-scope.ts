import { create } from "zustand"
import { createJSONStorage, persist } from "zustand/middleware"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"

type Scope = Pick<
  LedgerQueryParams,
  "accountId" | "accountIds" | "accountHolders" | "startDate" | "endDate"
>
export type AnalysisPopulation = "working" | "verified"
const emptyScope: Scope = {}
const ownerKey = () => {
  const user = useAuthStore.getState().user
  return user?.id || user?.username
}
const scopeKey = (caseId: string, owner = ownerKey()) =>
  owner ? JSON.stringify([owner, caseId]) : caseId

// Applied filters follow investigation tabs and survive refresh in this browser
// tab. Each signed-in user's case scope is separate from everyone else's.
export const useInvestigationScopeStore = create<{
  scopes: Record<string, Scope>
  populations: Record<string, AnalysisPopulation>
  apply: (caseId: string, scope: Scope) => void
  setPopulation: (caseId: string, value: AnalysisPopulation) => void
  reset: () => void
}>()(
  persist(
    (set) => ({
      scopes: {},
      populations: {},
      apply: (caseId, scope) =>
        set((state) => ({
          scopes: {
            ...state.scopes,
            [scopeKey(caseId)]: {
              accountId: scope.accountId,
              accountIds: scope.accountIds,
              accountHolders: scope.accountHolders,
              startDate: scope.startDate,
              endDate: scope.endDate,
            },
          },
        })),
      setPopulation: (caseId, value) =>
        set((state) => ({
          populations: { ...state.populations, [scopeKey(caseId)]: value },
        })),
      reset: () => set({ scopes: {}, populations: {} }),
    }),
    {
      name: "loupe-investigation-scope",
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        scopes: state.scopes,
        populations: state.populations,
      }),
    }
  )
)

function useScopeKey(caseId: string | undefined) {
  const owner = useAuthStore((state) => state.user?.id || state.user?.username)
  return caseId ? scopeKey(caseId, owner) : undefined
}

export function useInvestigationScope(caseId: string | undefined) {
  const key = useScopeKey(caseId)
  const scope = useInvestigationScopeStore((state) =>
    key ? (state.scopes[key] ?? emptyScope) : emptyScope
  )
  const apply = useInvestigationScopeStore((state) => state.apply)
  return [
    scope,
    (value: Scope) => {
      if (caseId) apply(caseId, value)
    },
  ] as const
}

export function useAnalysisPopulation(caseId: string | undefined) {
  const key = useScopeKey(caseId)
  const population = useInvestigationScopeStore((state) =>
    key ? (state.populations[key] ?? "working") : "working"
  )
  const set = useInvestigationScopeStore((state) => state.setPopulation)
  return [
    population,
    (value: string) => {
      if (caseId && (value === "working" || value === "verified"))
        set(caseId, value)
    },
  ] as const
}
