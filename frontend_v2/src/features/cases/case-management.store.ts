import { create } from "zustand"

type ViewMode = "my_cases" | "all_cases"
type SortBy = "updated_at" | "next_deadline"

interface CaseManagementStore {
  selectedCaseId: string | null
  viewMode: ViewMode
  sortBy: SortBy
  setSelectedCaseId: (id: string | null) => void
  setViewMode: (mode: ViewMode) => void
  setSortBy: (sortBy: SortBy) => void
}

export const useCaseManagementStore = create<CaseManagementStore>((set) => ({
  selectedCaseId: null,
  viewMode: "my_cases",
  sortBy: "updated_at",

  setSelectedCaseId: (id) => set({ selectedCaseId: id }),

  setViewMode: (mode) => set({ viewMode: mode }),

  setSortBy: (sortBy) => set({ sortBy }),

}))
