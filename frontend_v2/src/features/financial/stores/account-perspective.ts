import { create } from "zustand"
import type { AccountParties } from "../lib/account-parties"

type Perspective = { accountIds: string[]; partyCapture: AccountParties | null }
const empty: Perspective = { accountIds: [], partyCapture: null }

// Keep the investigator's account group while moving between tabs. A saved
// party-link capture remains the same capture, not a claim about later edits.
export const useAccountPerspectiveStore = create<{
  cases: Record<string, Perspective>
  set: (caseId: string, value: Perspective) => void
  reset: () => void
}>((set) => ({
  cases: {},
  set: (caseId, value) => {
    if (value.partyCapture && value.partyCapture.case_id !== caseId)
      throw Error("The account links belong to another case.")
    set((state) => ({
      cases: {
        ...state.cases,
        [caseId]: { ...value, accountIds: [...new Set(value.accountIds)] },
      },
    }))
  },
  reset: () => set({ cases: {} }),
}))

export function useAccountPerspective(caseId: string) {
  const value = useAccountPerspectiveStore(
    (state) => state.cases[caseId] ?? empty
  )
  const set = useAccountPerspectiveStore((state) => state.set)
  return [value, (next: Perspective) => set(caseId, next)] as const
}
