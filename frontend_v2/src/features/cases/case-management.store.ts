import { create } from "zustand"

type ViewMode = "my_cases" | "all_cases"
type SortBy = "updated_at" | "next_deadline"

interface CaseManagementStore {
  selectedCaseId: string | null
  viewMode: ViewMode
  sortBy: SortBy
  expandedSections: Set<string>
  setSelectedCaseId: (id: string | null) => void
  setViewMode: (mode: ViewMode) => void
  setSortBy: (sortBy: SortBy) => void
  toggleSection: (section: string) => void
}

export const useCaseManagementStore = create<CaseManagementStore>((set) => ({
  selectedCaseId: null,
  viewMode: "my_cases",
  sortBy: "updated_at",
  expandedSections: new Set(["deadlines", "snapshots"]),

  setSelectedCaseId: (id) => set({ selectedCaseId: id }),

  setViewMode: (mode) => set({ viewMode: mode }),

  setSortBy: (sortBy) => set({ sortBy }),

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
