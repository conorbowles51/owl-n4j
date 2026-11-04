import { useEffect, useState } from "react"
import { presenceBeat } from "@/features/phones/review-share"

/** One beat per open thread every 45 s (under 1 per 30 s), none while the tab is hidden; the server forgets a
 * person 100 s after their last beat, and at once when they leave the thread. */
export const PRESENCE_BEAT_MS = 45_000

export function useThreadPresence(caseId: string, threadKey: string | null | undefined) {
  const [words, setWords] = useState<string | null>(null)
  useEffect(() => {
    setWords(null)
    if (!caseId || !threadKey) return
    let live = true
    const beat = () => {
      if (typeof document !== "undefined" && document.hidden) return
      Promise.resolve()
        .then(() => presenceBeat(caseId, threadKey))
        .then((r) => live && setWords(r?.words ?? null))
        .catch(() => live && setWords(null)) // presence is a courtesy: a failed beat never blocks reading
    }
    beat()
    const timer = setInterval(beat, PRESENCE_BEAT_MS)
    return () => {
      live = false
      clearInterval(timer)
      Promise.resolve().then(() => presenceBeat(caseId, threadKey, true)).catch(() => undefined)
    }
  }, [caseId, threadKey])
  return words
}
