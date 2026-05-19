import type { CellebriteRecord, PhoneReport } from "../../types"
import {
  asText,
  readList,
  readNumber,
  readText,
  reportKey,
  reportTitle,
} from "../shared/cellebrite-format"

export type CommunicationSortField =
  | "call_count"
  | "message_count"
  | "email_count"
export type CommunicationSortDir = "asc" | "desc"

export function contactKey(contact: CellebriteRecord): string {
  return readText(contact, ["person_key", "key", "id", "node_key"], "unknown")
}

export function contactName(contact: CellebriteRecord): string {
  return readText(
    contact,
    ["name", "display_name", "label", "person_key", "key"],
    "Unknown"
  )
}

export function contactPhone(contact: CellebriteRecord): string {
  const phone = readText(contact, ["phone", "phone_number", "identifier"])
  if (phone) return phone
  return readList(contact, ["phone_numbers", "all_identifiers"])[0] ?? ""
}

export function contactDevices(contact: CellebriteRecord): string[] {
  return readList(contact, [
    "devices",
    "device_keys",
    "report_keys",
    "reports",
  ]).filter(Boolean)
}

export function contactCallCount(contact: CellebriteRecord): number {
  return readNumber(contact, ["call_count", "calls", "calls_count"])
}

export function contactMessageCount(contact: CellebriteRecord): number {
  return readNumber(contact, ["message_count", "messages", "messages_count"])
}

export function contactEmailCount(contact: CellebriteRecord): number {
  return readNumber(contact, ["email_count", "emails", "emails_count"])
}

export function contactTotal(contact: CellebriteRecord): number {
  return (
    contactCallCount(contact) +
    contactMessageCount(contact) +
    contactEmailCount(contact)
  )
}

export function contactSearchText(contact: CellebriteRecord): string {
  return [
    contactName(contact),
    contactPhone(contact),
    contactKey(contact),
    contactDevices(contact).join(" "),
    asText(contact.phone_numbers),
    asText(contact.all_identifiers),
  ]
    .join(" ")
    .toLowerCase()
}

export function compareContacts(
  a: CellebriteRecord,
  b: CellebriteRecord,
  field: CommunicationSortField,
  dir: CommunicationSortDir
): number {
  const value = (contact: CellebriteRecord) => {
    if (field === "message_count") return contactMessageCount(contact)
    if (field === "email_count") return contactEmailCount(contact)
    return contactCallCount(contact)
  }
  const diff = value(a) - value(b)
  if (diff !== 0) return dir === "desc" ? -diff : diff
  return contactName(a).localeCompare(contactName(b))
}

export function reportTitleMap(reports: PhoneReport[]): Map<string, string> {
  const map = new Map<string, string>()
  reports.forEach((report) => {
    const key = reportKey(report)
    if (key) map.set(key, reportTitle(report))
  })
  return map
}
