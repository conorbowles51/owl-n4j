import { create } from "zustand"
import { persist } from "zustand/middleware"

interface ModalEntry {
  id: string
  component: string
  props?: Record<string, unknown>
}

export type GraphPanelTab = "detail" | "chat"
export type GraphPanelToolOverlay =
  | "force-controls"
  | "analysis"
  | "similar"
  | "cypher"
  | "recycle"
  | null

interface UIStore {
  sidebarExpanded: boolean
  modalStack: ModalEntry[]
  commandPaletteOpen: boolean
  chatPanelOpen: boolean

  /* Graph side panel */
  graphPanelCollapsed: boolean
  graphPanelTab: GraphPanelTab
  graphPanelToolOverlay: GraphPanelToolOverlay

  toggleSidebar: () => void
  openModal: (entry: ModalEntry) => void
  closeModal: (id?: string) => void
  setCommandPaletteOpen: (open: boolean) => void
  setChatPanelOpen: (open: boolean) => void

  /* Graph panel actions */
  setGraphPanelCollapsed: (collapsed: boolean) => void
  setGraphPanelTab: (tab: GraphPanelTab) => void
  expandGraphPanelTo: (tab: GraphPanelTab) => void
  setGraphPanelToolOverlay: (overlay: GraphPanelToolOverlay) => void
}

const PERSISTED_KEYS = ["graphPanelCollapsed", "graphPanelTab"] as const

export const useUIStore = create<UIStore>()(
  persist(
    (set) => ({
      sidebarExpanded: true,
      modalStack: [],
      commandPaletteOpen: false,
      chatPanelOpen: false,

      /* Graph side panel */
      graphPanelCollapsed: true,
      graphPanelTab: "detail",
      graphPanelToolOverlay: null,

      toggleSidebar: () =>
        set((s) => ({ sidebarExpanded: !s.sidebarExpanded })),

      openModal: (entry) =>
        set((s) => ({ modalStack: [...s.modalStack, entry] })),

      closeModal: (id) =>
        set((s) => ({
          modalStack: id
            ? s.modalStack.filter((m) => m.id !== id)
            : s.modalStack.slice(0, -1),
        })),

      setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),

      setChatPanelOpen: (open) => set({ chatPanelOpen: open }),

      /* Graph panel actions */
      setGraphPanelCollapsed: (collapsed) =>
        set({ graphPanelCollapsed: collapsed, graphPanelToolOverlay: null }),

      setGraphPanelTab: (tab) => set({ graphPanelTab: tab }),

      expandGraphPanelTo: (tab) =>
        set({ graphPanelCollapsed: false, graphPanelTab: tab, graphPanelToolOverlay: null }),

      setGraphPanelToolOverlay: (overlay) =>
        set((s) => ({
          graphPanelToolOverlay: overlay,
          graphPanelCollapsed: overlay ? false : s.graphPanelCollapsed,
        })),
    }),
    {
      name: "owl-graph-panel",
      partialize: (state) => ({
        graphPanelCollapsed: state.graphPanelCollapsed,
        graphPanelTab: state.graphPanelTab,
      }),
    }
  )
)
