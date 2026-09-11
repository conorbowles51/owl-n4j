import { create } from "zustand"
import { createJSONStorage, persist } from "zustand/middleware"
import { useAuthStore } from "@/features/auth/hooks/use-auth"

// Browser-tab drafts are separate from saved casework records. Scope every
// value to the signed-in user and case so navigation cannot mix investigations.
export const useFinancialDraftStore = create<{
  drafts: Record<string, unknown>
  put: (key: string, value: unknown) => void
  remove: (key: string) => void
}>()(
  persist(
    (set) => ({
      drafts: {},
      put: (key, value) =>
        set((state) => ({ drafts: { ...state.drafts, [key]: value } })),
      remove: (key) =>
        set((state) => {
          const drafts = { ...state.drafts }
          delete drafts[key]
          return { drafts }
        }),
    }),
    {
      name: "loupe-financial-drafts",
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({ drafts: state.drafts }),
    }
  )
)

export function useFinancialDraft<T>(caseId: string, name: string, initial: T) {
  const owner = useAuthStore(
    (state) => state.user?.id || state.user?.username || "anonymous"
  )
  const key = `${owner}:${caseId}:${name}`
  const stored = useFinancialDraftStore((state) => state.drafts[key])
  const value = stored === undefined ? initial : (stored as T)
  const update = (next: T | ((previous: T) => T)) => {
    const previous = useFinancialDraftStore.getState().drafts[key] as
      | T
      | undefined
    useFinancialDraftStore
      .getState()
      .put(
        key,
        typeof next === "function"
          ? (next as (previous: T) => T)(previous ?? initial)
          : next
      )
  }
  return [
    value,
    update,
    () => useFinancialDraftStore.getState().remove(key),
  ] as const
}
