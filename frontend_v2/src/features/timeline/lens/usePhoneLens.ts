import { useEffect, useState } from "react"

const KEY = (caseId: string) => `loupe.timeline.phones.${caseId}`

type Stored = { on: boolean; emptyAtFirstUse: boolean }

function readStored(caseId: string): Stored | null {
  try {
    const v = JSON.parse(localStorage.getItem(KEY(caseId)) ?? "null")
    return v && typeof v.on === "boolean" ? { on: v.on, emptyAtFirstUse: !!v.emptyAtFirstUse } : null
  } catch {
    return null
  }
}

function writeStored(caseId: string, v: Stored) {
  try {
    localStorage.setItem(KEY(caseId), JSON.stringify(v))
  } catch {
    /* storage refused: the choice lasts for this page only */
  }
}

/**
 * The Phones lens switch (03 section 9.5; 07 section 4.12): on at first use when the case has no other dated events,
 * off otherwise. That choice is stored for this case at first use and never recomputed from the case's contents;
 * when the case later gains other events the screen says so.
 */
export function usePhoneLens(caseId: string, hasOtherEvents: boolean, hasPhones: boolean, ready = true) {
  const [state, setState] = useState<Stored | null>(() => (caseId ? readStored(caseId) : null))
  // stored only once the case has loaded completely (ready), never from a failed read
  const first = !state && caseId && hasPhones && ready ? { on: !hasOtherEvents, emptyAtFirstUse: !hasOtherEvents } : null
  const current = state ?? first
  useEffect(() => {
    if (!first) return
    writeStored(caseId, first) // stored once, at first use, never recomputed from the case's contents
    setState(first)
  }, [caseId, first?.on]) // eslint-disable-line react-hooks/exhaustive-deps
  const on = hasPhones && !!current?.on
  const note = on && current?.emptyAtFirstUse && hasOtherEvents ? "Phone entries are shown. This case now also has documents." : null
  const setOn = (v: boolean) => {
    const next = { on: v, emptyAtFirstUse: current?.emptyAtFirstUse ?? false }
    writeStored(caseId, next)
    setState(next)
  }
  return { on, setOn, note }
}
