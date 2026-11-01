import { useSyncExternalStore } from "react"

/**
 * Switches for work that is not released to everyone (07 12.1 item D: the phone prototype "behind a switch that
 * is off"). A switch is per browser and off unless turned on with ?<name>=on in the address (and off again with
 * ?<name>=off). It needs no release to flip, so a moderated session can turn it on for one participant's browser
 * only. Storage failures leave every switch off (07 4.2 item 13).
 */
export type SwitchName = "phone-prototype"
const KNOWN: SwitchName[] = ["phone-prototype"]
const key = (name: SwitchName) => `loupe.switch.${name}`
const listeners = new Set<() => void>()

export function isSwitchOn(name: SwitchName): boolean {
  try {
    return localStorage.getItem(key(name)) === "on"
  } catch {
    return false
  }
}

export function setSwitch(name: SwitchName, on: boolean) {
  try {
    if (on) localStorage.setItem(key(name), "on")
    else localStorage.removeItem(key(name))
  } catch {
    /* storage unavailable: the switch stays off */
  }
  for (const l of listeners) l()
}

/** Reads ?phone-prototype=on|off from the address; called once when the app starts and on navigation. */
export function applySwitchesFromSearch(search: string) {
  const q = new URLSearchParams(search)
  for (const name of KNOWN) {
    const v = q.get(name)
    if (v === "on") setSwitch(name, true)
    if (v === "off") setSwitch(name, false)
  }
}

export function useSwitch(name: SwitchName): boolean {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => isSwitchOn(name),
    () => false
  )
}
