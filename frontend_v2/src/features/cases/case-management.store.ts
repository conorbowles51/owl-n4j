import { create } from "zustand"

type ViewMode = "my_cases" | "all_cases"

interface CaseManagementStore {
  selectedCaseId: string | null
  viewMode: ViewMode
  expandedSections: Set<string>
  setSelectedCaseId: (id: string | null) => void
  setViewMode: (mode: ViewMode) => void
  toggleSection: (section: string) => void
}

export const useCaseManagementStore = create<CaseManagementStore>((set) => ({
  selectedCaseId: null,
  viewMode: "my_cases",
  expandedSections: new Set(["snapshots"]),

  setSelectedCaseId: (id) => set({ selectedCaseId: id }),

  setViewMode: (mode) => set({ viewMode: mode }),

  toggleSection: (section) =>
    set((state) => {
      const next = new Set(state.expandedSections)
      if (next.has(section)) {
        next.delete(section)
      } else {
        next.add(section)
      }
      return { expandedSections: next }
    }),
}))
