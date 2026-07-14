import { useEffect, useMemo, useState } from "react"
import {
  ChevronDown,
  ChevronRight,
  Mail,
  MessageSquare,
  Phone,
  PhoneIncoming,
  PhoneMissed,
  PhoneOutgoing,
  Smartphone,
  Trash2,
  User,
  Video,
  X,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { cn } from "@/lib/cn"

import type {
  CellebriteRecord,
  CommsItem,
  CommsParty,
  CommsType,
  PhoneReport,
  RailSelection,
} from "../../types"
import { useContactCommsFeed } from "../../hooks/use-cellebrite"
import { compactNumber, readList, readText } from "../shared/cellebrite-format"
import { PhoneReportChip } from "../shared/PhoneReportChip"
import { SmallEmpty } from "../shared/SmallEmpty"
import {
  ALL_COMMS_TYPES,
  dateSeparator,
  durationText,
  isOwnerParty,
  itemId,
  itemKind,
  messageTitle,
  partyKey,
  partyName,
  previewText,
  recipients,
  sender,
  shortDate,
  sourceAppLabel,
  typeLabel,
} from "../comms/commsUtils"
import { CommsAttachments } from "../comms/CommsAttachment"
import {
  contactDevices,
  contactKey as getContactKey,
  contactName,
  contactPhone,
} from "./communicationsUtils"

type Palette = {
  bubble: string
  text: string
  avatar: string
  avatarText: string
}

type FeedRow =
  | { kind: "separator"; date: string; label: string }
  | { kind: "item"; item: CommsItem; firstInRun: boolean }

const PALETTES: Palette[] = [
  {
    bubble: "bg-sky-500/12",
    text: "text-sky-950 dark:text-sky-100",
    avatar: "bg-sky-500",
    avatarText: "text-white",
  },
  {
    bubble: "bg-emerald-500/12",
    text: "text-emerald-950 dark:text-emerald-100",
    avatar: "bg-emerald-500",
    avatarText: "text-white",
  },
  {
    bubble: "bg-amber-500/15",
    text: "text-amber-950 dark:text-amber-100",
    avatar: "bg-amber-500",
    avatarText: "text-white",
  },
  {
    bubble: "bg-rose-500/12",
    text: "text-rose-950 dark:text-rose-100",
    avatar: "bg-rose-500",
    avatarText: "text-white",
  },
  {
    bubble: "bg-cyan-500/12",
    text: "text-cyan-950 dark:text-cyan-100",
    avatar: "bg-cyan-500",
    avatarText: "text-white",
  },
]

const TYPE_META: Record<
  CommsType,
  { icon: typeof MessageSquare; activeClass: string }
> = {
  message: {
    icon: MessageSquare,
    activeClass:
      "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  },
  call: {
    icon: Phone,
    activeClass:
      "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  },
  email: {
    icon: Mail,
    activeClass:
      "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  },
}

export function ContactFeedDrawer({
  caseId,
  contact,
  reportKeys,
  reports,
  onClose,
  onSelect,
}: {
  caseId: string
  contact: CellebriteRecord
  reportKeys: string[] | null
  reports: PhoneReport[]
  onClose: () => void
  onSelect: (selection: RailSelection) => void
}) {
  const [activeTypes, setActiveTypes] = useState<Set<CommsType>>(
    () => new Set<CommsType>(ALL_COMMS_TYPES)
  )
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null)

  const drillKey = getContactKey(contact)
  const activeTypeList = useMemo(
    () => ALL_COMMS_TYPES.filter((type) => activeTypes.has(type)),
    [activeTypes]
  )

  const feedQuery = useContactCommsFeed(
    caseId,
    drillKey,
    { reportKeys, types: activeTypeList, limit: 1000, offset: 0 },
    Boolean(drillKey)
  )

  const items = useMemo(
    () => feedQuery.data?.items ?? [],
    [feedQuery.data?.items]
  )
  const counts = useMemo(() => countItems(items), [items])
  const rows = useMemo(() => buildFeedRows(items), [items])
  const palette = useMemo(
    () => buildPalette(items, feedQuery.data?.contact),
    [feedQuery.data?.contact, items]
  )

  const seenReportKeys = useMemo(() => {
    const keys = new Set<string>()
    items.forEach((item) => {
      const key = itemReportKey(item)
      if (key) keys.add(key)
    })
    if (keys.size === 0) {
      contactDevices(contact).forEach((key) => keys.add(key))
    }
    return [...keys]
  }, [contact, items])

  const headerContact = feedQuery.data?.contact
  const title = headerContact?.name || contactName(contact)
  const phoneNumbers = useMemo(() => {
    const fromFeed = headerContact?.phone_numbers?.filter(Boolean) ?? []
    if (fromFeed.length) return fromFeed
    const fromContact = readList(contact, ["phone_numbers", "all_identifiers"])
    const phone = contactPhone(contact)
    return phone
      ? [phone, ...fromContact.filter((value) => value !== phone)]
      : fromContact
  }, [contact, headerContact?.phone_numbers])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])

  const toggleType = (type: CommsType) => {
    setActiveTypes((current) => {
      const next = new Set(current)
      if (next.has(type)) {
        if (next.size === 1) return next
        next.delete(type)
      } else {
        next.add(type)
      }
      return next
    })
  }

  const selectItem = (item: CommsItem) => {
    const id = itemId(item)
    setSelectedItemId(id)
    onSelect({
      id,
      kind: "message",
      title: messageTitle(item),
      payload: item,
    })
  }

  return (
    <div className="fixed inset-y-0 right-0 z-40 flex w-[38vw] min-w-[480px] max-w-[760px] flex-col border-l border-border bg-card shadow-2xl">
      <div className="flex shrink-0 items-center gap-2 border-b border-border bg-muted/60 px-4 py-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-sky-500/15">
          <User className="size-4 text-sky-600" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold">{title}</div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
            {(headerContact?.is_phone_owner ||
              contact.is_phone_owner === true) && (
              <Badge
                variant="success"
                className="h-5 gap-1 rounded-md px-1.5 text-[10px]"
              >
                <Smartphone className="size-3" />
                Phone owner
              </Badge>
            )}
            {phoneNumbers.slice(0, 3).map((phone) => (
              <span key={phone} className="font-mono text-foreground/80">
                {phone}
              </span>
            ))}
            {phoneNumbers.length > 3 && <span>+{phoneNumbers.length - 3}</span>}
          </div>
          {seenReportKeys.length > 0 && (
            <div className="mt-1 flex flex-wrap items-center gap-1">
              <span className="text-[10px] text-muted-foreground">Seen on</span>
              {seenReportKeys.map((key) => (
                <PhoneReportChip
                  key={key}
                  reportKey={key}
                  reports={reports}
                  compact
                />
              ))}
            </div>
          )}
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose} title="Close">
          <X className="size-4" />
        </Button>
      </div>

      <div className="flex shrink-0 items-center gap-2 border-b border-border bg-card px-3 py-2">
        <div className="flex items-center gap-1">
          {ALL_COMMS_TYPES.map((type) => {
            const meta = TYPE_META[type]
            const Icon = meta.icon
            const active = activeTypes.has(type)
            return (
              <button
                key={type}
                type="button"
                onClick={() => toggleType(type)}
                className={cn(
                  "flex h-8 items-center gap-1.5 rounded-md border border-border px-2 text-xs font-semibold text-muted-foreground transition-colors hover:text-foreground",
                  active && meta.activeClass
                )}
              >
                <Icon className="size-3.5" />
                {typeLabel(type)}
                <span className="rounded bg-background/70 px-1 font-mono text-[10px]">
                  {compactNumber(counts[type])}
                </span>
              </button>
            )
          })}
        </div>
        <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          {feedQuery.isFetching && <LoadingSpinner size="sm" />}
          <span>
            {compactNumber(feedQuery.data?.total ?? items.length)} total
          </span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto bg-muted/20 py-2">
        {feedQuery.isLoading ? (
          <SmallEmpty label="Loading contact feed" />
        ) : feedQuery.isError ? (
          <SmallEmpty label="Could not load contact feed" />
        ) : rows.length === 0 ? (
          <SmallEmpty label="No communications for this contact" />
        ) : (
          <div className="space-y-1">
            {rows.map((row, index) => {
              if (row.kind === "separator") {
                return (
                  <div
                    key={`${row.date || "unknown"}-${index}`}
                    className="flex justify-center py-2"
                  >
                    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
                      {row.label || "(no date)"}
                    </span>
                  </div>
                )
              }
              return (
                <FeedItemRow
                  key={itemId(row.item, `feed-${index}`)}
                  item={row.item}
                  reports={reports}
                  selected={selectedItemId === itemId(row.item)}
                  palette={palette}
                  firstInRun={row.firstInRun}
                  onItemSelect={selectItem}
                />
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function FeedItemRow({
  item,
  reports,
  selected,
  palette,
  firstInRun,
  onItemSelect,
}: {
  item: CommsItem
  reports: PhoneReport[]
  selected: boolean
  palette: Map<string, Palette>
  firstInRun: boolean
  onItemSelect: (item: CommsItem) => void
}) {
  const kind = itemKind(item)
  if (kind === "call") {
    return (
      <CallRow
        item={item}
        reports={reports}
        selected={selected}
        onItemSelect={onItemSelect}
      />
    )
  }
  if (kind === "email") {
    return (
      <EmailCard
        item={item}
        reports={reports}
        selected={selected}
        onItemSelect={onItemSelect}
      />
    )
  }
  return (
    <MessageBubble
      item={item}
      reports={reports}
      selected={selected}
      palette={palette}
      firstInRun={firstInRun}
      onItemSelect={onItemSelect}
    />
  )
}

function MessageBubble({
  item,
  reports,
  selected,
  palette,
  firstInRun,
  onItemSelect,
}: {
  item: CommsItem
  reports: PhoneReport[]
  selected: boolean
  palette: Map<string, Palette>
  firstInRun: boolean
  onItemSelect: (item: CommsItem) => void
}) {
  const from = sender(item)
  const fromKey = partyKey(from) || "unknown"
  const fromName = partyName(from)
  const owner = isOwnerParty(from)
  const color = palette.get(fromKey) ?? PALETTES[0]
  const message = readText(item, ["body", "summary", "label"], "")
  const tos = recipients(item)
  const toLabel = tos.length
    ? tos.map(partyName).join(", ")
    : partyName(item.counterpart)
  const report = itemReportKey(item)

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onItemSelect(item)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") onItemSelect(item)
      }}
      className={cn(
        "flex px-3 py-0.5 outline-none transition-colors",
        owner ? "justify-end" : "justify-start",
        selected
          ? "bg-amber-500/10 ring-1 ring-amber-500/40"
          : "hover:bg-muted/40"
      )}
    >
      <div
        className={cn(
          "flex max-w-[78%] items-end gap-2",
          owner && "flex-row-reverse"
        )}
      >
        <div className="w-7 shrink-0">
          {firstInRun && (
            <div
              className={cn(
                "flex size-7 items-center justify-center rounded-full text-[10px] font-semibold",
                color.avatar,
                color.avatarText
              )}
            >
              {initials(fromName)}
            </div>
          )}
        </div>
        <div
          className={cn(
            "flex min-w-0 flex-col",
            owner ? "items-end" : "items-start"
          )}
        >
          {firstInRun && (
            <div
              className={cn(
                "mb-0.5 flex max-w-full items-center gap-1 px-1 text-[11px]",
                owner && "flex-row-reverse"
              )}
            >
              <span className="truncate font-semibold">{fromName}</span>
              {owner && (
                <span className="inline-flex items-center gap-0.5 rounded border border-emerald-500/30 bg-emerald-500/10 px-1 text-[9px] uppercase tracking-wide text-emerald-700 dark:text-emerald-300">
                  <Smartphone className="size-2.5" />
                  You
                </span>
              )}
              {toLabel && (
                <span className="truncate text-muted-foreground">
                  to{" "}
                  <span className="font-medium text-foreground/80">
                    {toLabel}
                  </span>
                </span>
              )}
            </div>
          )}
          <div
            className={cn(
              "rounded-2xl border border-border px-3 py-1.5 shadow-sm",
              owner ? "rounded-br-sm" : "rounded-bl-sm",
              color.bubble,
              color.text
            )}
          >
            {readText(item, ["deleted_state"]) && (
              <div className="mb-1 flex items-center gap-1 text-[10px] text-red-600">
                <Trash2 className="size-3" />
                {readText(item, ["deleted_state"])}
              </div>
            )}
            {message ? (
              <div className="whitespace-pre-wrap break-words text-sm">
                {message}
              </div>
            ) : (
              <div className="text-sm italic text-muted-foreground">
                (empty message)
              </div>
            )}
            <CommsAttachments attachments={item.attachments ?? []} />
          </div>
          <div
            className={cn(
              "mt-0.5 flex items-center gap-1 px-1 text-[10px] text-muted-foreground",
              owner && "flex-row-reverse text-right"
            )}
          >
            <span>
              {shortDate(item.timestamp)}
              {sourceAppLabel(item) !== "Unknown"
                ? ` / ${sourceAppLabel(item)}`
                : ""}
            </span>
            {report && (
              <PhoneReportChip reportKey={report} reports={reports} compact />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function CallRow({
  item,
  reports,
  selected,
  onItemSelect,
}: {
  item: CommsItem
  reports: PhoneReport[]
  selected: boolean
  onItemSelect: (item: CommsItem) => void
}) {
  const direction = readText(item, ["direction", "call_type"]).toLowerCase()
  const missed = direction.includes("miss")
  const outgoing = direction.includes("out")
  const incoming = direction.includes("in")
  const Icon = missed
    ? PhoneMissed
    : outgoing
      ? PhoneOutgoing
      : incoming
        ? PhoneIncoming
        : Phone
  const fromName = partyName(sender(item))
  const toName =
    recipients(item).map(partyName).join(", ") || partyName(item.counterpart)
  const report = itemReportKey(item)

  return (
    <button
      type="button"
      onClick={() => onItemSelect(item)}
      className={cn(
        "flex w-full items-center gap-3 border-y border-border/60 px-4 py-2 text-left transition-colors",
        selected
          ? "bg-amber-500/10 ring-1 ring-amber-500/40"
          : "bg-card/70 hover:bg-muted/50"
      )}
    >
      <Icon
        className={cn(
          "size-4 shrink-0",
          missed
            ? "text-red-500"
            : outgoing
              ? "text-emerald-500"
              : "text-sky-500"
        )}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-sm">
          <span className="truncate font-medium">{fromName}</span>
          <span className="text-muted-foreground">to</span>
          <span className="truncate font-medium">{toName}</span>
          {Boolean(item.video_call) && (
            <Video className="size-3 text-muted-foreground" />
          )}
          {missed && (
            <Badge variant="destructive" className="h-5 text-[10px]">
              Missed
            </Badge>
          )}
          {report && (
            <PhoneReportChip
              reportKey={report}
              reports={reports}
              compact
              className="ml-auto"
            />
          )}
        </div>
        <div className="text-[11px] text-muted-foreground">
          {shortDate(item.timestamp)}
          {readText(item, ["duration"])
            ? ` / ${durationText(readText(item, ["duration"]))}`
            : ""}
          {sourceAppLabel(item) !== "Unknown"
            ? ` / ${sourceAppLabel(item)}`
            : ""}
        </div>
        <CommsAttachments attachments={item.attachments ?? []} />
      </div>
    </button>
  )
}

function EmailCard({
  item,
  reports,
  selected,
  onItemSelect,
}: {
  item: CommsItem
  reports: PhoneReport[]
  selected: boolean
  onItemSelect: (item: CommsItem) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const body = readText(item, ["body", "summary"], "")
  const hasHtml = /<[a-z][\s\S]*>/i.test(body)
  const fromName = partyName(sender(item))
  const toName =
    recipients(item).map(partyName).join(", ") || partyName(item.counterpart)
  const report = itemReportKey(item)

  return (
    <div
      className={cn(
        "border-y border-border/60 bg-card/80",
        selected && "bg-amber-500/10 ring-1 ring-amber-500/40"
      )}
    >
      <button
        type="button"
        onClick={() => {
          setExpanded((value) => !value)
          onItemSelect(item)
        }}
        className="flex w-full items-start gap-2 px-4 py-2 text-left transition-colors hover:bg-muted/50"
      >
        <Mail className="mt-0.5 size-4 shrink-0 text-amber-500" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 text-sm">
            {expanded ? (
              <ChevronDown className="size-3" />
            ) : (
              <ChevronRight className="size-3" />
            )}
            <span className="truncate font-medium">
              {readText(item, ["subject", "label"], "(no subject)")}
            </span>
            {report && (
              <PhoneReportChip
                reportKey={report}
                reports={reports}
                compact
                className="ml-auto"
              />
            )}
          </div>
          <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <span className="truncate">
              {fromName} to {toName}
            </span>
            <span className="shrink-0">/ {shortDate(item.timestamp)}</span>
          </div>
          {!expanded && body && (
            <div className="mt-1 truncate text-xs text-muted-foreground">
              {previewText(item, 160)}
            </div>
          )}
        </div>
      </button>
      {expanded && (
        <div className="ml-8 px-4 pb-3">
          {hasHtml ? (
            <iframe
              title="email-body"
              className="h-72 w-full rounded-md border border-border bg-background"
              sandbox=""
              srcDoc={`<html><head><meta charset="utf-8"><style>body{font-family:"Source Sans 3",system-ui,sans-serif;font-size:13px;line-height:1.45;padding:10px;color:#0b202a;margin:0}img{max-width:100%;height:auto}a{color:#067278}</style></head><body>${body}</body></html>`}
            />
          ) : (
            <pre className="whitespace-pre-wrap rounded-md border border-border bg-muted/30 p-3 font-sans text-xs text-foreground">
              {body || "(empty email body)"}
            </pre>
          )}
          <CommsAttachments attachments={item.attachments ?? []} />
        </div>
      )}
    </div>
  )
}

function buildFeedRows(items: CommsItem[]): FeedRow[] {
  const rows: FeedRow[] = []
  let currentDate = ""
  let lastSender = ""
  items.forEach((item) => {
    const date = String(item.timestamp ?? "").slice(0, 10)
    if (date !== currentDate) {
      currentDate = date
      lastSender = ""
      rows.push({
        kind: "separator",
        date,
        label: dateSeparator(item.timestamp),
      })
    }
    const itemSender = partyKey(sender(item)) || "unknown"
    const firstInRun = itemSender !== lastSender || itemKind(item) !== "message"
    lastSender = itemKind(item) === "message" ? itemSender : ""
    rows.push({ kind: "item", item, firstInRun })
  })
  return rows
}

function countItems(items: CommsItem[]): Record<CommsType, number> {
  return items.reduce<Record<CommsType, number>>(
    (acc, item) => {
      acc[itemKind(item)] += 1
      return acc
    },
    { message: 0, call: 0, email: 0 }
  )
}

function buildPalette(
  items: CommsItem[],
  contact?: CommsParty | null
): Map<string, Palette> {
  const map = new Map<string, Palette>()
  const participants: CommsParty[] = []
  if (contact) participants.push(contact)
  items.forEach((item) => {
    const from = sender(item)
    if (from) participants.push(from as CommsParty)
    recipients(item).forEach((party) => participants.push(party as CommsParty))
    if (item.counterpart) participants.push(item.counterpart)
  })

  const owner = participants.find(isOwnerParty)
  if (owner) {
    const key = partyKey(owner)
    if (key) map.set(key, PALETTES[0])
  }

  let index = owner ? 1 : 0
  participants.forEach((participant) => {
    const key = partyKey(participant)
    if (!key || map.has(key)) return
    map.set(key, PALETTES[index % PALETTES.length])
    index += 1
  })
  return map
}

function itemReportKey(item: CommsItem): string {
  return readText(item, [
    "report_key",
    "cellebrite_report_key",
    "device_report_key",
  ])
}

function initials(value: string): string {
  const parts = value.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return "?"
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase()
}
