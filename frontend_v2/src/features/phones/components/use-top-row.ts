import { useEffect, useRef } from "react"
import type { StreamRow } from "../schemas"
import type { UseStream } from "../hooks/use-stream"

/**
 * Reports the first message in view when that message changes. The stream object is new on every page render and when
 * focus moves, so a report only on a real change keeps it from overwriting the row the person moved to.
 */
export function useTopRow(stream: Pick<UseStream, "count" | "item">, topIndex: number | null, rowsVersion: number, onTopRow?: (row: StreamRow) => void) {
  const reported = useRef<string | null>(null)
  useEffect(() => {
    if (topIndex === null || !onTopRow) return
    for (let i = topIndex; i < Math.min(topIndex + 3, stream.count); i++) {
      const it = stream.item(i)
      if (it.type !== "row" || !it.row) continue // a header, or a row of a window not loaded yet
      if (reported.current !== it.row.event_uid) {
        reported.current = it.row.event_uid
        onTopRow(it.row)
      }
      return
    }
  }, [topIndex, stream, onTopRow, rowsVersion])
}
