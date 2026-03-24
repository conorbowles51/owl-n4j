import { create } from "zustand"

type StatusFilter = "all" | "unprocessed" | "processing" | "processed" | "failed"

interface EvidenceState {
  // Navigation
  currentFolderId: string | null
  setCurrentFolder: (id: string | null) => void

  // Folder tree
  expandedFolderIds: Set<string>
  toggleFolderExpand: (id: string) => void
  expandFolder: (id: string) => void
  collapseFolder: (id: string) => void

  // Selection
  selectedFileIds: Set<string>
  selectedFolderIds: Set<string>
  toggleFileSelection: (id: string) => void
  toggleFolderSelection: (id: string) => void
  selectAllFiles: (ids: string[]) => void
  clearSelection: () => void

  // Detail sheet
  detailFileId: string | null
  detailOpen: boolean
  openDetail: (fileId: string) => void
  closeDetail: () => void

  // Jobs panel
  jobsPanelOpen: boolean
  toggleJobsPanel: () => void
  setJobsPanelOpen: (open: boolean) => void

  // Filters
  searchTerm: string
  setSearchTerm: (term: string) => void
  statusFilter: StatusFilter
  setStatusFilter: (filter: StatusFilter) => void
  typeFilter: string
  setTypeFilter: (filter: string) => void

  // Drag state
  dragType: "file" | "folder" | "external" | null
  dragId: string | null
  setDrag: (type: "file" | "folder" | "external" | null, id: string | null) => void
  clearDrag: () => void

  // Case tracking
  _currentCaseId: string | null
  resetForCase: (caseId: string) => void
}

export const useEvidenceStore = create<EvidenceState>((set) => ({
  currentFolderId: null,
  setCurrentFolder: (id) => set({ currentFolderId: id, selectedFileIds: new Set(), selectedFolderIds: new Set() }),

  expandedFolderIds: new Set(),
  toggleFolderExpand: (id) =>
    set((s) => {
      const next = new Set(s.expandedFolderIds)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return { expandedFolderIds: next }
    }),
  expandFolder: (id) =>
    set((s) => {
      const next = new Set(s.expandedFolderIds)
      next.add(id)
      return { expandedFolderIds: next }
    }),
  collapseFolder: (id) =>
    set((s) => {
      const next = new Set(s.expandedFolderIds)
      next.delete(id)
      return { expandedFolderIds: next }
    }),

  selectedFileIds: new Set(),
  selectedFolderIds: new Set(),
  toggleFileSelection: (id) =>
    set((s) => {
      const next = new Set(s.selectedFileIds)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return { selectedFileIds: next }
    }),
  toggleFolderSelection: (id) =>
    set((s) => {
      const next = new Set(s.selectedFolderIds)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return { selectedFolderIds: next }
    }),
  selectAllFiles: (ids) => set({ selectedFileIds: new Set(ids) }),
  clearSelection: () => set({ selectedFileIds: new Set(), selectedFolderIds: new Set() }),

  detailFileId: null,
  detailOpen: false,
  openDetail: (fileId) => set({ detailFileId: fileId, detailOpen: true }),
  closeDetail: () => set({ detailOpen: false }),

  jobsPanelOpen: false,
  toggleJobsPanel: () => set((s) => ({ jobsPanelOpen: !s.jobsPanelOpen })),
  setJobsPanelOpen: (open) => set({ jobsPanelOpen: open }),

  searchTerm: "",
  setSearchTerm: (term) => set({ searchTerm: term }),
  statusFilter: "all",
  setStatusFilter: (filter) => set({ statusFilter: filter }),
  typeFilter: "",
  setTypeFilter: (filter) => set({ typeFilter: filter }),

  dragType: null,
  dragId: null,
  setDrag: (type, id) => set({ dragType: type, dragId: id }),
  clearDrag: () => set({ dragType: null, dragId: null }),

  _currentCaseId: null,
  resetForCase: (caseId) =>
    set((s) => {
      if (s._currentCaseId === caseId) return s
      return {
        _currentCaseId: caseId,
        currentFolderId: null,
        expandedFolderIds: new Set(),
        selectedFileIds: new Set(),
        selectedFolderIds: new Set(),
        detailFileId: null,
        detailOpen: false,
        searchTerm: "",
        statusFilter: "all" as StatusFilter,
        typeFilter: "",
      }
    }),
}))
