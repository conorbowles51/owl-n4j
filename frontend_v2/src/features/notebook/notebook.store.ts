import { create } from "zustand"
import type { NotebookLinkInput } from "./api"

interface NotebookState {
  activeNoteId: string | null
  draftLinks: NotebookLinkInput[]
  draftIntentId: number
  openNote: (noteId: string) => void
  startDraft: (links?: NotebookLinkInput[]) => void
  clearActiveNote: () => void
}

export const useNotebookStore = create<NotebookState>((set) => ({
  activeNoteId: null,
  draftLinks: [],
  draftIntentId: 0,
  openNote: (noteId) => set({ activeNoteId: noteId }),
  startDraft: (links = []) =>
    set((state) => ({
      activeNoteId: null,
      draftLinks: links,
      draftIntentId: state.draftIntentId + 1,
    })),
  clearActiveNote: () => set({ activeNoteId: null }),
}))
