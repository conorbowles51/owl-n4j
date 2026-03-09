import { create } from "zustand"
import type { EvidenceFile } from "@/types/evidence.types"

type EvidenceTab = "files" | "upload" | "profiles" | "activity"
type StatusFilter = "all" | "unprocessed" | "processing" | "processed" | "failed"

interface EvidenceState {
  // Selection
  selectedFileIds: Set<string>
  toggleFileSelection: (id: string) => void
  selectAllFiles: (ids: string[]) => void
  clearSelection: () => void

  // Tabs
  activeTab: EvidenceTab
  setActiveTab: (tab: EvidenceTab) => void

  // Detail sheet
  detailFile: EvidenceFile | null
  detailOpen: boolean
  openDetail: (file: EvidenceFile) => void
  closeDetail: () => void

  // Filters
  searchTerm: string
  setSearchTerm: (term: string) => void
  statusFilter: StatusFilter
  setStatusFilter: (filter: StatusFilter) => void
  typeFilter: string
  setTypeFilter: (filter: string) => void
}

export const useEvidenceStore = create<EvidenceState>((set) => ({
  selectedFileIds: new Set(),
  toggleFileSelection: (id) =>
    set((state) => {
      const next = new Set(state.selectedFileIds)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return { selectedFileIds: next }
    }),
  selectAllFiles: (ids) => set({ selectedFileIds: new Set(ids) }),
  clearSelection: () => set({ selectedFileIds: new Set() }),

  activeTab: "files",
  setActiveTab: (tab) => set({ activeTab: tab }),

  detailFile: null,
  detailOpen: false,
  openDetail: (file) => set({ detailFile: file, detailOpen: true }),
  closeDetail: () => set({ detailOpen: false }),

  searchTerm: "",
  setSearchTerm: (term) => set({ searchTerm: term }),
  statusFilter: "all",
  setStatusFilter: (filter) => set({ statusFilter: filter }),
  typeFilter: "",
  setTypeFilter: (filter) => set({ typeFilter: filter }),
}))
