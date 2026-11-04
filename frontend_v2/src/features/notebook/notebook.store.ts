import { create } from "zustand"
import type { NotebookLinkInput } from "./api"

/** A note started from phone messages (07 section 6, CO-6): how many were selected and how many messages the links
 * carry, and the records to pin beside the composer. */
export interface DraftPhone {
  caseId: string
  selected: number
  linked: number
  recordIds: string[]
}

interface NotebookState {
  activeNoteId: string | null
  draftLinks: NotebookLinkInput[]
  draftPhone: DraftPhone | null
  draftIntentId: number
  openNote: (noteId: string) => void
  startDraft: (links?: NotebookLinkInput[], phone?: DraftPhone | null) => void
  clearActiveNote: () => void
}

export const useNotebookStore = create<NotebookState>((set) => ({
  activeNoteId: null,
  draftLinks: [],
  draftPhone: null,
  draftIntentId: 0,
  openNote: (noteId) => set({ activeNoteId: noteId }),
  startDraft: (links = [], phone = null) =>
    set((state) => ({
      activeNoteId: null,
      draftLinks: links,
      draftPhone: phone,
      draftIntentId: state.draftIntentId + 1,
    })),
  clearActiveNote: () => set({ activeNoteId: null }),
}))
