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
    let sending: string | null = null
    const save = () => {
      const row = readRow.current
      if (!row) return
      if (start === null) {
        start = row.event_uid
        return
      }
      if (row.event_uid === start && saved === null) return
      if (row.event_uid === saved || row.event_uid === sending) return
      const inBrowser = () => {
        if (extraction) rememberSpot(caseId, { thread: threadKey, extraction, record: row.event_uid, at: new Date().toISOString() })
        saved = row.event_uid
      }
      if (!assigned) return inBrowser()
      sending = row.event_uid
      saveReviewPosition(caseId, threadKey, row)
        .then((r) => {
          if (r.saved > 0) saved = row.event_uid
          else inBrowser() // no longer this person's task: the position is not lost
        })
        .catch(() => undefined) // saved stays as it was, so the next beat tries again; reading is never interrupted
        .finally(() => { sending = null })
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
