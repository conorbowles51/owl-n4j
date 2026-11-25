import { useEffect, useSyncExternalStore } from "react"
import { mentionsAPI, type MentionMarkView } from "./api"

/** The marks of the records on screen: rows ask for their own record, and the asks of one moment go out as one
 * request per case (at most 200 records each). */

type Entry = MentionMarkView[] | undefined
const cache = new Map<string, Entry>()
const waiting = new Map<string, Set<string>>()
const listeners = new Set<() => void>()
let timer: ReturnType<typeof setTimeout> | null = null

const key = (caseId: string, uid: string) => `${caseId}|${uid}`

function flush() {
  timer = null
  for (const [caseId, uids] of waiting) {
    const list = [...uids]
    waiting.delete(caseId)
    for (let i = 0; i < list.length; i += 200) {
      const part = list.slice(i, i + 200)
      mentionsAPI
        .marks(caseId, part)
        .then((r) => {
          for (const u of part) cache.set(key(caseId, u), r.marks[u] ?? [])
        })
        .catch(() => {
          for (const u of part) cache.set(key(caseId, u), [])
        })
        .finally(() => listeners.forEach((l) => l()))
    }
  }
}

function ask(caseId: string, uid: string) {
  if (cache.has(key(caseId, uid))) return
  cache.set(key(caseId, uid), undefined)
  const set = waiting.get(caseId) ?? new Set<string>()
  set.add(uid)
  waiting.set(caseId, set)
  if (!timer) timer = setTimeout(flush, 30)
}

/** Forget the marks of a case, after a reading or a correction changed them. */
export function forgetMentionMarks(caseId: string) {
  for (const k of [...cache.keys()]) if (k.startsWith(`${caseId}|`)) cache.delete(k)
  listeners.forEach((l) => l())
}

function subscribe(l: () => void) {
  listeners.add(l)
  return () => listeners.delete(l)
}

export function useMentionMarks(caseId: string | undefined, recordUid: string | undefined): MentionMarkView[] {
  useEffect(() => {
    if (caseId && recordUid) ask(caseId, recordUid)
  }, [caseId, recordUid])
  const got = useSyncExternalStore(subscribe, () => (caseId && recordUid ? cache.get(key(caseId, recordUid)) : undefined))
  return got ?? EMPTY
}
const EMPTY: MentionMarkView[] = []

