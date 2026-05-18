import type { CellebriteRecord } from "../../types"
import { isRecord, readList, readNumber, readText } from "../shared/cellebrite-format"

export function unifiedContactId(row: CellebriteRecord): string {
  return readText(row, ["canonical", "canonical_phone", "display_number", "phone", "key"], readList(row, ["person_keys"])[0] ?? "contact")
}

export function unifiedDisplayNumber(row: CellebriteRecord): string {
  return (
    readText(row, ["display_number", "canonical", "canonical_phone", "phone"]) ||
    aliasName(unifiedAliases(row)[0]) ||
    "No canonical number"
  )
}

export function unifiedAliases(row: CellebriteRecord | null | undefined): CellebriteRecord[] {
  if (!row || !Array.isArray(row.aliases)) return []
  return row.aliases.filter(isRecord)
}

export function aliasName(alias: CellebriteRecord | undefined): string {
  return readText(alias, ["name", "display_name", "label", "key"], "")
}

export function aliasKey(alias: CellebriteRecord, fallback: string): string {
  return readText(alias, ["key", "id", "name"], fallback)
}

export function unifiedReportKeys(row: CellebriteRecord | null | undefined): string[] {
  return readList(row, ["report_keys", "device_report_keys"])
}

export function unifiedPersonKeys(row: CellebriteRecord | null | undefined): string[] {
  return readList(row, ["person_keys", "participant_keys", "entity_keys"])
}

export function unifiedMessageCount(row: CellebriteRecord | null | undefined): number {
  return readNumber(row, ["msg_count", "message_count", "messages"])
}

export function unifiedCallCount(row: CellebriteRecord | null | undefined): number {
  return readNumber(row, ["call_count", "calls"])
}

export function unifiedEmailCount(row: CellebriteRecord | null | undefined): number {
  return readNumber(row, ["email_count", "emails"])
}

export function unifiedInteractionCount(row: CellebriteRecord | null | undefined): number {
  const explicit = readNumber(row, ["interactions", "total"], -1)
  if (explicit >= 0) return explicit
  return unifiedMessageCount(row) + unifiedCallCount(row) + unifiedEmailCount(row)
}

export function unifiedMatchesSearch(row: CellebriteRecord, search: string): boolean {
  const needle = search.trim().toLowerCase()
  if (!needle) return true
  const haystack = [
    readText(row, ["canonical", "canonical_phone", "display_number", "phone"]),
    ...unifiedAliases(row).map(aliasName),
    ...unifiedReportKeys(row),
  ]
  return haystack.some((value) => value.toLowerCase().includes(needle))
}
