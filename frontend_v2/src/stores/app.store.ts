import { create } from "zustand"

interface AppStore {
  sidebarExpanded: boolean
  commandPaletteOpen: boolean
  toggleSidebar: () => void
  setSidebarExpanded: (expanded: boolean) => void
  setCommandPaletteOpen: (open: boolean) => void
}

export const useAppStore = create<AppStore>((set) => ({
  sidebarExpanded: true,
  commandPaletteOpen: false,

  toggleSidebar: () =>
    set((s) => ({ sidebarExpanded: !s.sidebarExpanded })),

  setSidebarExpanded: (expanded) => set({ sidebarExpanded: expanded }),

  setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),
}))
