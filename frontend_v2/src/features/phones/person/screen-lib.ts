import { useMemo, type CSSProperties } from "react"
import { phoneMark } from "../lib/phone-palette"
import { useCasePhones } from "../ui/use-case-phones"

/** Shared by screens 3 and 4: one colour per phone everywhere (COMMON rule 1), numbers and UTC times in words. */

/** Each phone's palette index in the case (one colour per phone everywhere, COMMON rule 1). */
export function usePhoneIndex(caseId: string): (id: string) => number {
  const phones = useCasePhones(caseId)
  return useMemo(() => {
    const m = new Map(phones.map((p) => [p.id, p.index]))
    return (id: string) => m.get(id) ?? 0
  }, [phones])
}

/** Props that fill an element with a phone's colour in light and dark (the palette's per-theme values). */
export function phoneFill(index: number, className = "", style: CSSProperties = {}) {
  const m = phoneMark(index)
  return {
    className: `${className} bg-[var(--phone-light)] dark:bg-[var(--phone-dark)]`,
    style: { ...style, ["--phone-light" as string]: m.light, ["--phone-dark" as string]: m.dark } as CSSProperties,
  }
}

export const fmt = (n: number) => n.toLocaleString("en-US")

export function plural(n: number, one: string, many: string) {
  return `${fmt(n)} ${n === 1 ? one : many}`
}

/** "3 Jan 2024" in UTC, the zone the screens state. */
export function day(iso: string | null | undefined) {
  if (!iso) return "no date"
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })
}

export function clock(iso: string) {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" })
}

