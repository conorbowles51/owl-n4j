import { useSyncExternalStore } from "react"

/**
 * Per-browser switches. Each has a default: the phone prototype is off unless turned on with ?phone-prototype=on
 * (07 12.1 item D); Corroborate is on for everyone and ?corroborate-v2=off turns it off for one browser. ?<name>=on
 * or =off sets the switch in this browser; it needs no release to flip. When storage fails, each switch keeps its
 * default (07 4.2 item 13).
 */
export type SwitchName = "phone-prototype" | "corroborate-v2"
const KNOWN: SwitchName[] = ["phone-prototype", "corroborate-v2"]
const DEFAULT_ON: Record<SwitchName, boolean> = { "phone-prototype": false, "corroborate-v2": true }
const key = (name: SwitchName) => `loupe.switch.${name}`
const listeners = new Set<() => void>()

export function isSwitchOn(name: SwitchName): boolean {
  try {
    const v = localStorage.getItem(key(name))
    return v === "on" ? true : v === "off" ? false : DEFAULT_ON[name]
  } catch {
    return DEFAULT_ON[name]
  }
}

export function setSwitch(name: SwitchName, on: boolean) {
  try {
    if (on === DEFAULT_ON[name]) localStorage.removeItem(key(name))
    else localStorage.setItem(key(name), on ? "on" : "off")
  } catch {
    /* storage unavailable: the switch keeps its default */
  }
  for (const l of listeners) l()
}

/** Reads ?<switch>=on|off from the address; called once when the app starts and on navigation. */
export function applySwitchesFromSearch(search: string) {
  const q = new URLSearchParams(search)
  for (const name of KNOWN) {
    const v = q.get(name)
    if (v === "on") setSwitch(name, true)
    if (v === "off") setSwitch(name, false)
  }
}

/** At app start, before routing: a redirect such as /cases/:id to its workspace drops the query string. */
export function applySwitchesAtStart(address: { search: string } = window.location) {
  applySwitchesFromSearch(address.search)
}

export function useSwitch(name: SwitchName): boolean {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => isSwitchOn(name),
    () => DEFAULT_ON[name]
  )
}
