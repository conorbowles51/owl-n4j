/**
 * The kit's time words now come from the one formatter, lib/evidence-time.ts (03 section 3.2): every time string on
 * screen, in copy and in the PDF is written by it. Kept as a module so the kit and the prototype keep their imports.
 */
import { dayOf, formatFull, formatRowTime, offsetMinutes, offsetText, zoneLabel } from "@/lib/evidence-time"

export function offsetWords(iso: string, zone: string): string {
  return offsetText(offsetMinutes(Date.parse(iso), zone))
}

/** "Eastern Time (UTC-5)" for the instant's day. */
export function zoneWords(iso: string, zone: string): string {
  return zoneLabel(dayOf(iso, zone) as string, zone)
}

/** The full form, "Tue, Mar 5, 2024, 3:04:05 PM EST" (detail views, copy and export always carry seconds). */
export function instantWords(iso: string, zone: string, _withSeconds = true): string {
  void _withSeconds
  return formatFull(iso, zone)
}

/** The row's short time: "3:04 PM"; seconds when asked. */
export function timeOfDay(iso: string, zone: string, withSeconds = false): string {
  return formatRowTime(iso, zone, withSeconds)
}
