import { create } from "zustand"

interface ModalEntry {
  id: string
  component: string
  props?: Record<string, unknown>
}

interface UIStore {
  sidebarExpanded: boolean
  modalStack: ModalEntry[]
  commandPaletteOpen: boolean
  chatPanelOpen: boolean

  toggleSidebar: () => void
  openModal: (entry: ModalEntry) => void
  closeModal: (id?: string) => void
  setCommandPaletteOpen: (open: boolean) => void
  setChatPanelOpen: (open: boolean) => void
}

export const useUIStore = create<UIStore>((set) => ({
  sidebarExpanded: true,
  modalStack: [],
  commandPaletteOpen: false,
  chatPanelOpen: false,

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
}))
