import { create } from "zustand"
import type { CaseworkLinkInput } from "../casework-api"

/**
 * The phone items a person has selected on a phone screen (07 section 6.4 item 10). Phone screens set it; the
 * Workspace and Notebook offer it as part of the current selection. A selection over 500 records is one
 * `phone_selection` link carrying its frozen record list, so `links` stays small while `recordCount` states the
 * whole total.
 */
export interface PhoneSelection {
  caseId: string
  links: CaseworkLinkInput[]
  recordCount: number
  screen: string
}

interface PhoneSelectionStore {
  selection: PhoneSelection | null
  setSelection: (selection: PhoneSelection | null) => void
  clear: () => void
}

export const usePhoneSelectionStore = create<PhoneSelectionStore>((set) => ({
  selection: null,
  setSelection: (selection) => set({ selection }),
  clear: () => set({ selection: null }),
}))
