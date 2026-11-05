import { useSyncExternalStore } from "react"
import { activeBindings, subscribeKeymap } from "@/lib/keymap"

let snapshot = activeBindings()
let snapshotKey = JSON.stringify(snapshot)
function readBindings() {
  const next = activeBindings()
  const key = JSON.stringify(next)
  if (key !== snapshotKey) {
    snapshot = next
    snapshotKey = key
  }
  return snapshot
}

/** The keys of the current screen, from the registry (07 4.9). */
export function useBindings() {
  return useSyncExternalStore(subscribeKeymap, readBindings, readBindings)
}
