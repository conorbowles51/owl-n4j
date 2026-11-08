import { createContext, useContext } from "react"

/** What the page showing payments offers a reading check: opening that payment in the check panel. */
export type ReadingCheck = {
  /** Open the payment in the check panel; closing the panel returns to the same row. */
  openPanel?: (paymentId: string) => void
}

export const ReadingCheckContext = createContext<ReadingCheck>({})

export function useReadingCheck() {
  return useContext(ReadingCheckContext)
}

/**
 * Bring a payment's row back into view (and focus its label) after the check panel opens or closes beside the table.
 * Rows are found by key (`data-reading-row`), never by index: large ledgers are virtualised and re-sorted.
 * Two frames: the table has settled into its new width before the row is looked for.
 */
export function showReadingRow(id: string | null, focus: boolean) {
  if (!id) return
  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      const mark = document.querySelector<HTMLElement>(`[data-reading-row="${CSS.escape(id)}"]`)
      mark?.scrollIntoView({ block: "nearest" })
      if (focus) (mark?.matches("[tabindex]") ? mark : mark?.querySelector<HTMLElement>("button"))?.focus({ preventScroll: true })
    })
  )
}
