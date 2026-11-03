import type { PhoneChipProps } from "./PhoneChip"

export function shortDate(iso: string): string {
  const d = new Date(`${iso.slice(0, 10)}T12:00:00Z`)
  return d.toLocaleDateString("en-US", { day: "numeric", month: "short", timeZone: "UTC" }).replace(/^(\w+) (\d+)$/, "$2 $1")
}

export function phoneChipText({ label, extractionDate, collides }: Pick<PhoneChipProps, "label" | "extractionDate" | "collides">) {
  return collides && extractionDate ? `${label} · ${shortDate(extractionDate)}` : label
}
