import { useEffect, type RefObject } from "react"
import { rememberSpot } from "@/features/phones/lib/continue-reading"
import { saveReviewPosition } from "@/features/phones/review-share"

export interface ReadRow {
  event_uid: string
  instant: string | null
}

/** Looked at this often while a thread is open; a save happens only when the row moved, so at most one request. */
export const POSITION_BEAT_MS = 10_000
const FIRST_LOOK_MS = 3_000

/**
 * The reading position (07 J-15, UXD-36): on an assigned review it goes to the task's link on the server, so it
 * survives the browser and passes to a colleague; otherwise it stays in this browser, as a record id. The row the
 * thread opened on is not a position: only a row the person moved to is saved, so opening a thread never overwrites
 * where someone stopped.
 */
export function useReadingPosition(caseId: string, threadKey: string, extraction: string | null, readRow: RefObject<ReadRow | null>, assigned: boolean) {
  useEffect(() => {
    let start: string | null = null
    let saved: string | null = null
    const save = () => {
      const row = readRow.current
      if (!row) return
      if (start === null) {
        start = row.event_uid
        return
      }
      if (row.event_uid === start && saved === null) return
      if (row.event_uid === saved) return
      saved = row.event_uid
      if (assigned) saveReviewPosition(caseId, threadKey, row).catch(() => undefined) // the next beat is the retry for a later row; reading is never interrupted
      else if (extraction) rememberSpot(caseId, { thread: threadKey, extraction, record: row.event_uid, at: new Date().toISOString() })
    }
    const look = () => {
      if (typeof document === "undefined" || !document.hidden) save()
    }
    const first = setTimeout(look, FIRST_LOOK_MS)
    const timer = setInterval(look, POSITION_BEAT_MS)
    return () => {
      clearTimeout(first)
      clearInterval(timer)
      if (start !== null) save()
    }
  }, [caseId, threadKey, extraction, readRow, assigned])
}
