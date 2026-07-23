import { useEffect, useMemo, useRef, useState } from "react"
import {
  ChevronDown,
  ChevronRight,
  Mail,
  MessageSquare,
  Phone,
  PhoneIncoming,
  PhoneMissed,
  PhoneOutgoing,
  Search,
  Smartphone,
  Trash2,
  Video,
  X,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/cn"

import type { CommsItem, CommsParty, CommsThread, ThreadDetailResponse } from "../../types"
import { compactNumber, readNumber, readText } from "../shared/cellebrite-format"
import { SmallEmpty } from "../shared/SmallEmpty"
import { CommsAttachments } from "./CommsAttachment"
import {
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
  reportLabel,
  sender,
  shortDate,
  sourceAppLabel,
  toDateInput,
} from "./commsUtils"

type Palette = {
  bubble: string
  text: string
  avatar: string
  avatarText: string
}

const PALETTE: Palette[] = [
  { bubble: "bg-sky-500/12", text: "text-sky-950 dark:text-sky-100", avatar: "bg-sky-500", avatarText: "text-white" },
  { bubble: "bg-emerald-500/12", text: "text-emerald-950 dark:text-emerald-100", avatar: "bg-emerald-500", avatarText: "text-white" },
  { bubble: "bg-amber-500/15", text: "text-amber-950 dark:text-amber-100", avatar: "bg-amber-500", avatarText: "text-white" },
  { bubble: "bg-rose-500/12", text: "text-rose-950 dark:text-rose-100", avatar: "bg-rose-500", avatarText: "text-white" },
  { bubble: "bg-cyan-500/12", text: "text-cyan-950 dark:text-cyan-100", avatar: "bg-cyan-500", avatarText: "text-white" },
]

export function CommsThreadView({
  caseId,
  thread,
  detail,
  loading,
  selectedItemId,
  reportsByKey,
  externalSearch,
  onLoadAllItems,
  onItemSelect,
}: {
  caseId: string
  thread: CommsThread | null
  detail: ThreadDetailResponse | undefined
  loading: boolean
  selectedItemId: string | null
  reportsByKey: Map<string, string>
  externalSearch: string
  onLoadAllItems?: () => void
  onItemSelect: (item: CommsItem) => void
}) {
  const [search, setSearch] = useState(externalSearch)
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const lastAutoScrolledThreadRef = useRef<string | null>(null)

  const items = useMemo(() => detail?.items ?? detail?.messages ?? [], [detail?.items, detail?.messages])
  const participants = useMemo(
    () => detail?.thread?.participants ?? thread?.participants ?? [],
    [detail?.thread?.participants, thread?.participants]
  )
  const palette = useMemo(() => buildPalette(participants), [participants])

  const filteredItems = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return items.filter((item) => {
      const date = toDateInput(item.timestamp)
      if (startDate && date && date < startDate) return false
      if (endDate && date && date > endDate) return false
      if (!needle) return true
      return [
        messageTitle(item),
        previewText(item, 500),
        sourceAppLabel(item),
        partyName(sender(item)),
        recipients(item).map(partyName).join(" "),
      ]
        .join(" ")
        .toLowerCase()
        .includes(needle)
    })
  }, [endDate, items, search, startDate])

  useEffect(() => {
    const key = thread ? `${thread.thread_type}:${thread.thread_id}` : null
    if (!key) {
      lastAutoScrolledThreadRef.current = null
      return
    }
    if (!scrollRef.current || loading || filteredItems.length === 0) return
    if (externalSearch || lastAutoScrolledThreadRef.current === key) return
    lastAutoScrolledThreadRef.current = key
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [externalSearch, thread, loading, filteredItems.length])

  if (!thread) {
    return (
      <div className="flex h-full items-center justify-center">
        <SmallEmpty label="Select a thread to view messages" />
      </div>
    )
  }

  const title = participantNames(participants) || thread.name || thread.thread_id
  const report = reportLabel(thread.report_key ?? thread.device_report_key, reportsByKey)
  const totalItems = readNumber(detail, ["total"], readNumber(thread, ["item_count", "message_count"], items.length))
  const hiddenItemCount = Math.max(0, totalItems - items.length)

  return (
    <div className="flex h-full min-h-0 w-full flex-col bg-muted/10">
      <div className="shrink-0 border-b border-border bg-card px-4 py-2">
        <div className="flex items-center gap-2">
          <ThreadIcon thread={thread} />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold">{title}</div>
            <div className="truncate text-[11px] text-muted-foreground">
              {sourceAppLabel(thread)} -{" "}
              {hiddenItemCount > 0
                ? `${compactNumber(items.length)} of ${compactNumber(totalItems)} items loaded`
                : `${compactNumber(totalItems)} items`}
            </div>
          </div>
          {report && (
            <Badge variant="outline" className="max-w-[220px] truncate">
              <Smartphone className="mr-1 size-3" />
              {report}
            </Badge>
          )}
        </div>
        {participants.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {participants.map((participant) => {
              const key = partyKey(participant) || partyName(participant)
              const color = palette.get(key) ?? PALETTE[0]
              return (
                <span
                  key={key}
                  className={cn(
                    "inline-flex max-w-[180px] items-center gap-1 rounded-full border border-border px-1.5 py-0.5 text-[10px]",
                    color.bubble,
                    color.text
                  )}
                  title={partyName(participant)}
                >
                  <span className={cn("flex size-4 items-center justify-center rounded-full text-[8px] font-semibold", color.avatar, color.avatarText)}>
                    {initials(partyName(participant))}
                  </span>
                  <span className="truncate">{partyName(participant)}</span>
                  {isOwnerParty(participant) && <Smartphone className="size-2.5" />}
                </span>
              )
            })}
          </div>
        )}
      </div>

      <div className="shrink-0 border-b border-border bg-card px-3 py-1.5">
        <div className="flex items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search this thread"
              className="h-8 pl-7 pr-8 text-xs"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="size-3.5" />
              </button>
            )}
          </div>
          <Input
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
            className="hidden h-8 w-36 text-xs md:block"
          />
          <Input
            type="date"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
            className="hidden h-8 w-36 text-xs md:block"
          />
          <Badge variant="slate" className="shrink-0">
            {compactNumber(filteredItems.length)} shown
          </Badge>
          {hiddenItemCount > 0 && onLoadAllItems && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onLoadAllItems}
              disabled={loading}
              className="h-8"
            >
              Load all {compactNumber(totalItems)}
            </Button>
          )}
        </div>
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto py-3">
        {loading ? (
          <SmallEmpty label="Loading thread" />
        ) : filteredItems.length === 0 ? (
          <SmallEmpty label="No items in this thread" />
        ) : (
          <ThreadItems
            caseId={caseId}
            items={filteredItems}
            selectedItemId={selectedItemId}
            palette={palette}
            onItemSelect={onItemSelect}
          />
        )}
      </div>
    </div>
  )
}

function ThreadIcon({ thread }: { thread: CommsThread }) {
  const type = String(thread.thread_type || "").toLowerCase()
  const Icon = type.includes("call") ? Phone : type.includes("email") ? Mail : MessageSquare
  return (
    <div className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-muted">
      <Icon className="size-4 text-amber-500" />
    </div>
  )
}

function ThreadItems({
  caseId,
  items,
  selectedItemId,
  palette,
  onItemSelect,
}: {
  caseId: string
  items: CommsItem[]
  selectedItemId: string | null
  palette: Map<string, Palette>
  onItemSelect: (item: CommsItem) => void
}) {
  const rows = useMemo(() => buildThreadRows(items), [items])

  return (
    <div className="space-y-1">
      {rows.map((row, index) => {
        if (row.kind === "separator") {
          return (
            <div key={`${row.date || "unknown"}-${index}-sep`} className="flex justify-center py-2">
              <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
                {row.label}
              </span>
            </div>
          )
        }
        return (
          <CommsItemRow
            key={itemId(row.item, `item-${index}`)}
            caseId={caseId}
            item={row.item}
            selected={selectedItemId === itemId(row.item)}
            palette={palette}
            firstInRun={row.firstInRun}
            onItemSelect={onItemSelect}
          />
        )
      })}
    </div>
  )
}

function CommsItemRow({
  item,
  selected,
  palette,
  firstInRun,
  onItemSelect,
}: {
  caseId: string
  item: CommsItem
  selected: boolean
  palette: Map<string, Palette>
  firstInRun: boolean
  onItemSelect: (item: CommsItem) => void
}) {
  const kind = itemKind(item)
  if (kind === "call") {
    return <CallRow item={item} selected={selected} onItemSelect={onItemSelect} />
  }
  if (kind === "email") {
    return <EmailCard item={item} selected={selected} onItemSelect={onItemSelect} />
  }
  return (
    <MessageBubble
      item={item}
      selected={selected}
      palette={palette}
      firstInRun={firstInRun}
      onItemSelect={onItemSelect}
    />
  )
}

type ThreadRenderRow =
  | { kind: "separator"; date: string; label: string }
  | { kind: "item"; item: CommsItem; firstInRun: boolean }

function buildThreadRows(items: CommsItem[]): ThreadRenderRow[] {
  const rows: ThreadRenderRow[] = []
  let currentDate = ""
  let lastSender = ""
  items.forEach((item) => {
    const date = String(item.timestamp ?? "").slice(0, 10)
    if (date !== currentDate) {
      currentDate = date
      lastSender = ""
      rows.push({ kind: "separator", date, label: dateSeparator(item.timestamp) })
    }
    const itemSender = partyKey(sender(item)) || "unknown"
    const firstInRun = itemSender !== lastSender || itemKind(item) !== "message"
    lastSender = itemKind(item) === "message" ? itemSender : ""
    rows.push({ kind: "item", item, firstInRun })
  })
  return rows
}

function MessageBubble({
  item,
  selected,
  palette,
  firstInRun,
  onItemSelect,
}: {
  item: CommsItem
  selected: boolean
  palette: Map<string, Palette>
  firstInRun: boolean
  onItemSelect: (item: CommsItem) => void
}) {
  const from = sender(item)
  const fromKey = partyKey(from) || "unknown"
  const fromName = partyName(from)
  const owner = isOwnerParty(from)
  const color = palette.get(fromKey) ?? PALETTE[0]
  const message = readText(item, ["body", "summary", "label"], "")
  const tos = recipients(item)
  const toLabel = tos.length ? tos.map(partyName).join(", ") : partyName(item.counterpart)

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
        selected ? "bg-amber-500/10 ring-1 ring-amber-500/40" : "hover:bg-muted/40"
      )}
    >
      <div className={cn("flex max-w-[78%] items-end gap-2", owner && "flex-row-reverse")}>
        <div className="w-7 shrink-0">
          {firstInRun && (
            <div className={cn("flex size-7 items-center justify-center rounded-full text-[10px] font-semibold", color.avatar, color.avatarText)}>
              {initials(fromName)}
            </div>
          )}
        </div>
        <div className={cn("flex min-w-0 flex-col", owner ? "items-end" : "items-start")}>
          {firstInRun && (
            <div className={cn("mb-0.5 flex max-w-full items-center gap-1 px-1 text-[11px]", owner && "flex-row-reverse")}>
              <span className="truncate font-semibold">{fromName}</span>
              {owner && (
                <span className="inline-flex items-center gap-0.5 rounded border border-emerald-500/30 bg-emerald-500/10 px-1 text-[9px] uppercase tracking-wide text-emerald-700 dark:text-emerald-300">
                  <Smartphone className="size-2.5" />
                  You
                </span>
              )}
              {toLabel && (
                <span className="truncate text-muted-foreground">
                  to <span className="font-medium text-foreground/80">{toLabel}</span>
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
              <div className="whitespace-pre-wrap break-words text-sm">{message}</div>
            ) : (
              <div className="text-sm italic text-muted-foreground">(empty message)</div>
            )}
            <CommsAttachments attachments={item.attachments ?? []} />
          </div>
          <div className={cn("mt-0.5 px-1 text-[10px] text-muted-foreground", owner && "text-right")}>
            {shortDate(item.timestamp)}
            {sourceAppLabel(item) !== "Unknown" ? ` · ${sourceAppLabel(item)}` : ""}
          </div>
        </div>
      </div>
    </div>
  )
}

function CallRow({
  item,
  selected,
  onItemSelect,
}: {
  item: CommsItem
  selected: boolean
  onItemSelect: (item: CommsItem) => void
}) {
  const direction = readText(item, ["direction", "call_type"]).toLowerCase()
  const missed = direction.includes("miss")
  const outgoing = direction.includes("out")
  const incoming = direction.includes("in")
  const Icon = missed ? PhoneMissed : outgoing ? PhoneOutgoing : incoming ? PhoneIncoming : Phone
  const fromName = partyName(sender(item))
  const toName = recipients(item).map(partyName).join(", ") || partyName(item.counterpart)

  return (
    <button
      type="button"
      onClick={() => onItemSelect(item)}
      className={cn(
        "flex w-full items-center gap-3 border-y border-border/60 px-4 py-2 text-left transition-colors",
        selected ? "bg-amber-500/10 ring-1 ring-amber-500/40" : "bg-card/70 hover:bg-muted/50"
      )}
    >
      <Icon className={cn("size-4 shrink-0", missed ? "text-red-500" : outgoing ? "text-emerald-500" : "text-sky-500")} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-sm">
          <span className="truncate font-medium">{fromName}</span>
          <span className="text-muted-foreground">to</span>
          <span className="truncate font-medium">{toName}</span>
          {Boolean(item.video_call) && <Video className="size-3 text-muted-foreground" />}
          {missed && <Badge variant="destructive" className="h-5 text-[10px]">Missed</Badge>}
        </div>
        <div className="text-[11px] text-muted-foreground">
          {shortDate(item.timestamp)}
          {readText(item, ["duration"]) ? ` · ${durationText(readText(item, ["duration"]))}` : ""}
          {sourceAppLabel(item) !== "Unknown" ? ` · ${sourceAppLabel(item)}` : ""}
        </div>
        <CommsAttachments attachments={item.attachments ?? []} />
      </div>
    </button>
  )
}

function EmailCard({
  item,
  selected,
  onItemSelect,
}: {
  item: CommsItem
  selected: boolean
  onItemSelect: (item: CommsItem) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const body = readText(item, ["body", "summary"], "")
  const hasHtml = /<[a-z][\s\S]*>/i.test(body)
  const fromName = partyName(sender(item))
  const toName = recipients(item).map(partyName).join(", ") || partyName(item.counterpart)

  return (
    <div className={cn("border-y border-border/60 bg-card/80", selected && "bg-amber-500/10 ring-1 ring-amber-500/40")}>
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
            {expanded ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
            <span className="truncate font-medium">{readText(item, ["subject", "label"], "(no subject)")}</span>
          </div>
          <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <span className="truncate">{fromName} to {toName}</span>
            <span className="shrink-0">· {shortDate(item.timestamp)}</span>
          </div>
          {!expanded && body && <div className="mt-1 truncate text-xs text-muted-foreground">{previewText(item, 160)}</div>}
        </div>
      </button>
      {expanded && (
        <div className="ml-8 px-4 pb-3">
          {hasHtml ? (
            <iframe
              title="email-body"
              className="h-72 w-full rounded-md border border-border bg-background"
              sandbox=""
              srcDoc={`<html><head><meta charset="utf-8"><style>body{font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:13px;line-height:1.45;padding:10px;color:#17181c;margin:0}img{max-width:100%;height:auto}a{color:#b41624}</style></head><body>${body}</body></html>`}
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

function buildPalette(participants: CommsParty[]): Map<string, Palette> {
  const map = new Map<string, Palette>()
  const owner = participants.find(isOwnerParty)
  if (owner) {
    const key = partyKey(owner)
    if (key) map.set(key, PALETTE[0])
  }
  let index = owner ? 1 : 0
  participants.forEach((participant) => {
    const key = partyKey(participant)
    if (!key || map.has(key)) return
    map.set(key, PALETTE[index % PALETTE.length])
    index += 1
  })
  return map
}

function participantNames(participants: CommsParty[]): string {
  const nonOwner = participants.filter((participant) => !isOwnerParty(participant))
  const visible = nonOwner.length ? nonOwner : participants
  return visible.slice(0, 3).map(partyName).filter(Boolean).join(", ")
}

function initials(value: string): string {
  const parts = value.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return "?"
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase()
}
