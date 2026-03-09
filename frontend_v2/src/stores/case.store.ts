import { create } from "zustand"

interface CaseStore {
  currentCaseId: string | null
  currentCaseName: string | null
  currentCaseVersion: string | null
  setActiveCase: (id: string, name: string, version?: string) => void
  clearActiveCase: () => void
}

export const useCaseStore = create<CaseStore>((set) => ({
  currentCaseId: null,
  currentCaseName: null,
  currentCaseVersion: null,

  setActiveCase: (id, name, version) =>
    set({
      currentCaseId: id,
      currentCaseName: name,
      currentCaseVersion: version ?? null,
    }),

  clearActiveCase: () =>
    set({
      currentCaseId: null,
      currentCaseName: null,
      currentCaseVersion: null,
    }),
}))
