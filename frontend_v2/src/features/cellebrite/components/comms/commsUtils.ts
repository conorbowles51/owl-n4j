import type {
  CellebriteRecord,
  CommsItem,
  CommsParty,
  CommsThread,
  CommsType,
  PhoneReport,
} from "../../types"
import { asText, compactDate, readText, reportKey, reportTitle, truncate } from "../shared/cellebrite-format"

export type ParticipantRole = "any" | "from" | "to"

export type ParticipantFilter = {
  key: string
  name: string
  role: ParticipantRole
}

export type CommsViewMode = "browse" | "read"

export type CommsParticipantMode = "split" | "any"

export const ALL_COMMS_TYPES: CommsType[] = ["message", "call", "email"]

const TYPE_TO_THREAD: Record<CommsType, string> = {
  message: "chat",
  call: "calls",
  email: "emails",
}

const TYPE_LABELS: Record<CommsType, string> = {
  message: "Messages",
  call: "Calls",
  email: "Emails",
}

export function typeLabel(type: CommsType): string {
  return TYPE_LABELS[type]
}

export function threadTypesForTypes(types: Set<CommsType>): string[] | null {
  const values = [...types].map((type) => TYPE_TO_THREAD[type]).filter(Boolean)
  return values.length === ALL_COMMS_TYPES.length ? null : values
}

export function typeArray(types: Set<CommsType>): CommsType[] | null {
  return types.size === ALL_COMMS_TYPES.length ? null : [...types]
}

export function threadKey(thread: Pick<CommsThread, "thread_id" | "thread_type">): string {
  return `${thread.thread_type}:${thread.thread_id}`
}

export function itemId(item: CommsItem, fallback = "item"): string {
  return readText(item, ["key", "node_key", "id", "message_id"], fallback)
}

export function reportLabelMap(reports: PhoneReport[]): Map<string, string> {
  const map = new Map<string, string>()
  reports.forEach((report) => {
    const key = reportKey(report)
    if (key) map.set(key, reportTitle(report))
  })
  return map
}

export function reportLabel(value: unknown, reportsByKey: Map<string, string>): string {
  const key = asText(value)
  if (!key) return ""
  return reportsByKey.get(key) ?? key
}

export function entityKey(row: CellebriteRecord): string {
  return readText(row, ["key", "id", "node_key", "identifier", "phone"])
}

export function entityName(row: CellebriteRecord): string {
  return readText(row, ["name", "display_name", "label", "identifier", "phone", "key"], "Unknown")
}

export function partyKey(party: CommsParty | CellebriteRecord | null | undefined): string {
  if (!party) return ""
  return readText(party, ["key", "id", "node_key", "identifier", "phone"])
}

export function partyName(party: CommsParty | CellebriteRecord | null | undefined): string {
  if (!party) return "Unknown"
  return readText(party, ["name", "display_name", "label", "identifier", "phone", "key"], "Unknown")
}

export function isOwnerParty(party: CommsParty | CellebriteRecord | null | undefined): boolean {
  if (!party) return false
  return party.is_owner === true || party.owner === true || party.role === "owner"
}

export function participantSummary(thread: CommsThread): {
  title: string
  extraCount: number
} {
  const participants = thread.participants ?? []
  const nonOwner = participants.filter((party) => !isOwnerParty(party))
  const visible = (nonOwner.length ? nonOwner : participants).slice(0, 2)
  const title = visible.map(partyName).filter(Boolean).join(", ") || thread.name || thread.thread_id
  return {
    title,
    extraCount: Math.max(0, participants.length - visible.length),
  }
}

export function sourceAppLabel(row: CellebriteRecord | null | undefined): string {
  return readText(row, ["source_app", "app", "name", "application"], "Unknown")
}

export function threadKindIcon(thread: CommsThread): "message" | "call" | "email" {
  const type = String(thread.thread_type || "").toLowerCase()
  if (type.includes("call")) return "call"
  if (type.includes("email")) return "email"
  return "message"
}

export function itemKind(item: CommsItem): CommsType {
  const raw = readText(item, ["type", "event_type", "thread_type"], "message").toLowerCase()
  if (raw.includes("call")) return "call"
  if (raw.includes("email") || raw.includes("mail")) return "email"
  return "message"
}

export function sender(item: CommsItem): CommsParty | CellebriteRecord | null {
  return (item.sender as CommsParty | undefined) ?? (item.from as CellebriteRecord | undefined) ?? null
}

export function recipients(item: CommsItem): (CommsParty | CellebriteRecord)[] {
  if (Array.isArray(item.recipients)) return item.recipients
  const record = item as CellebriteRecord
  const recipient = record.recipient ?? record.to ?? item.counterpart
  return recipient && typeof recipient === "object" && !Array.isArray(recipient)
    ? [recipient as CommsParty | CellebriteRecord]
    : []
}

export function messageTitle(item: CommsItem): string {
  const kind = itemKind(item)
  if (kind === "email") return readText(item, ["subject", "label"], "(no subject)")
  if (kind === "call") {
    const from = partyName(sender(item))
    const to = recipients(item).map(partyName).join(", ") || partyName(item.counterpart)
    return `${from} to ${to || "Unknown"}`
  }
  return truncate(readText(item, ["body", "summary", "label"], "Message"), 96)
}

export function previewText(item: CommsItem, length = 120): string {
  const raw = readText(item, ["body", "summary", "subject", "label"], "")
  return truncate(raw.replace(/\s+/g, " ").trim(), length)
}

export function shortDate(value: unknown): string {
  const text = asText(value)
  if (!text) return ""
  const date = new Date(text)
  if (Number.isNaN(date.getTime())) return text
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function dateSeparator(value: unknown): string {
  const text = asText(value)
  if (!text) return ""
  const date = new Date(text)
  if (Number.isNaN(date.getTime())) return text.slice(0, 10)
  return date.toLocaleDateString(undefined, {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

export function durationText(value: unknown): string {
  const text = asText(value)
  if (!text) return ""
  const parts = text.split(":").map((part) => Number.parseInt(part, 10))
  if (parts.length === 3 && parts.every(Number.isFinite)) {
    const [hours, minutes, seconds] = parts
    if (hours > 0) return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
    return `${minutes}:${String(seconds).padStart(2, "0")}`
  }
  return text
}

export function toDateInput(value: unknown): string {
  const text = asText(value)
  if (!text) return ""
  return text.slice(0, 10)
}

export function toLocaleDate(value: unknown): string {
  const text = asText(value)
  if (!text) return ""
  return compactDate(text).replace(/, 00:00$/, "")
}

export function seedParticipants(keys: string[]): ParticipantFilter[] {
  return keys.filter(Boolean).map((key) => ({ key, name: key, role: "any" }))
}

export function mergeSeedParticipants(
  current: ParticipantFilter[],
  keys: string[]
): ParticipantFilter[] {
  const byKey = new Map(current.map((participant) => [participant.key, participant]))
  keys.filter(Boolean).forEach((key) => {
    const existing = byKey.get(key)
    byKey.set(key, {
      key,
      name: existing?.name && existing.name !== existing.key ? existing.name : key,
      role: "any",
    })
  })
  return [...byKey.values()]
}

export function applyEntityNames(
  participants: ParticipantFilter[],
  entities: CellebriteRecord[]
): ParticipantFilter[] {
  if (!participants.length || !entities.length) return participants
  const entityByKey = new Map(entities.map((entity) => [entityKey(entity), entityName(entity)]))
  let changed = false
  const next = participants.map((participant) => {
    if (participant.name && participant.name !== participant.key) return participant
    const name = entityByKey.get(participant.key)
    if (!name || name === participant.name) return participant
    changed = true
    return { ...participant, name }
  })
  return changed ? next : participants
}

export function dedupeThreads(threads: CommsThread[]): CommsThread[] {
  const byGroup = new Map<string, CommsThread>()
  threads.forEach((thread) => {
    const participants = (thread.participants ?? [])
      .map(partyKey)
      .filter(Boolean)
      .sort()
      .join("|")
    const groupKey = [
      thread.report_key || thread.device_report_key || "",
      sourceAppLabel(thread),
      thread.thread_type,
      participants || thread.name || thread.thread_id,
    ].join("::")
    const current = byGroup.get(groupKey)
    if (!current) {
      byGroup.set(groupKey, thread)
      return
    }
    const currentCount = current.item_count ?? current.message_count ?? 0
    const nextCount = thread.item_count ?? thread.message_count ?? 0
    const currentParticipants = current.participants?.length ?? 0
    const nextParticipants = thread.participants?.length ?? 0
    if (nextCount > currentCount || (nextCount === currentCount && nextParticipants > currentParticipants)) {
      byGroup.set(groupKey, thread)
    }
  })
  return [...byGroup.values()]
}

