import { create } from "zustand"

/** Whether the Map's area comparison is open (lx-overlapviews-b A). */
export const useAreaCompare = create<{ open: boolean; show: () => void; close: () => void }>((set) => ({
  open: false,
  show: () => set({ open: true }),
  close: () => set({ open: false }),
}))
