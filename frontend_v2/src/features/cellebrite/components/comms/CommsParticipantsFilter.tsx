import { useMemo, useState } from "react"
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Filter,
  GitMerge,
  Search,
  Split,
  Smartphone,
  UserRound,
  X,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/cn"

import type { CellebriteRecord } from "../../types"
import { compactNumber, readNumber } from "../shared/cellebrite-format"
import type { CommsParticipantMode, ParticipantFilter } from "./commsUtils"
import { entityKey, entityName } from "./commsUtils"

const PAGE_SIZE = 50

export function CommsParticipantsFilter({
  entities,
  participants,
  mode,
  loading,
  onParticipantsChange,
  onModeChange,
}: {
  entities: CellebriteRecord[]
  participants: ParticipantFilter[]
  mode: CommsParticipantMode
  loading?: boolean
  onParticipantsChange: (participants: ParticipantFilter[]) => void
  onModeChange: (mode: CommsParticipantMode) => void
}) {
  const [collapsed, setCollapsed] = useState(false)
  const fromKeys = useMemo(() => {
    const set = new Set<string>()
    participants.forEach((participant) => {
      if (participant.role === "from" || participant.role === "any") set.add(participant.key)
    })
    return set
  }, [participants])
  const toKeys = useMemo(() => {
    const set = new Set<string>()
    participants.forEach((participant) => {
      if (participant.role === "to" || participant.role === "any") set.add(participant.key)
    })
    return set
  }, [participants])
  const anyKeys = useMemo(() => new Set(participants.map((participant) => participant.key)), [participants])

  function toggleSplit(bucket: "from" | "to", row: CellebriteRecord) {
    const key = entityKey(row)
    if (!key) return
    const name = entityName(row)
    const inFrom = fromKeys.has(key)
    const inTo = toKeys.has(key)
    const nextInFrom = bucket === "from" ? !inFrom : inFrom
    const nextInTo = bucket === "to" ? !inTo : inTo
    const next = participants.filter((participant) => participant.key !== key)
    if (nextInFrom && nextInTo) next.push({ key, name, role: "any" })
    else if (nextInFrom) next.push({ key, name, role: "from" })
    else if (nextInTo) next.push({ key, name, role: "to" })
    onParticipantsChange(next)
  }

  function toggleAny(row: CellebriteRecord) {
    const key = entityKey(row)
    if (!key) return
    if (anyKeys.has(key)) {
      onParticipantsChange(participants.filter((participant) => participant.key !== key))
      return
    }
    onParticipantsChange([...participants, { key, name: entityName(row), role: "any" }])
  }

  const isAny = mode === "any"

  return (
    <div className="shrink-0 border-b border-border bg-card">
      <div className="flex min-h-9 items-center gap-2 bg-muted/30 px-3 py-1">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 gap-1.5 px-2 text-xs"
          onClick={() => setCollapsed((value) => !value)}
        >
          {collapsed ? <ChevronRight className="size-3.5" /> : <ChevronDown className="size-3.5" />}
          <Filter className="size-3.5 text-amber-500" />
          <span className="font-semibold">Participants</span>
          <span className="text-muted-foreground">
            {isAny ? `(Any ${anyKeys.size})` : `(From ${fromKeys.size} / To ${toKeys.size})`}
          </span>
        </Button>
        <ModePill mode={mode} onChange={onModeChange} />
        {loading && <span className="text-[11px] text-muted-foreground">Loading people...</span>}
        <div className="flex-1" />
        {participants.length > 0 && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs text-muted-foreground"
            onClick={() => onParticipantsChange([])}
          >
            Clear all
          </Button>
        )}
      </div>

      {!collapsed && (
        isAny ? (
          <SidePanel
            title="Anyone involved"
            subtitle="Sender or recipient"
            entities={entities}
            selected={anyKeys}
            onToggle={toggleAny}
            wide
          />
        ) : (
          <div className="grid grid-cols-2 divide-x divide-border">
            <SidePanel
              title="From"
              subtitle="Sender"
              entities={entities}
              selected={fromKeys}
              onToggle={(entity) => toggleSplit("from", entity)}
            />
            <SidePanel
              title="To"
              subtitle="Recipient"
              entities={entities}
              selected={toKeys}
              onToggle={(entity) => toggleSplit("to", entity)}
            />
          </div>
        )
      )}

      {participants.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-border bg-muted/20 px-3 py-1.5">
          {participants.map((participant) => (
            <SelectedChip
              key={`${participant.role}:${participant.key}`}
              participant={participant}
              modeIsAny={isAny}
              onRemove={() =>
                onParticipantsChange(participants.filter((item) => item.key !== participant.key))
              }
            />
          ))}
        </div>
      )}
    </div>
  )
}

function ModePill({
  mode,
  onChange,
}: {
  mode: CommsParticipantMode
  onChange: (mode: CommsParticipantMode) => void
}) {
  const isAny = mode === "any"
  return (
    <div className="inline-flex overflow-hidden rounded-md border border-border text-[11px]">
      <button
        type="button"
        onClick={() => onChange("split")}
        className={cn(
          "inline-flex h-6 items-center gap-1 px-2 transition-colors",
          !isAny ? "bg-secondary text-secondary-foreground" : "bg-card text-muted-foreground hover:bg-muted"
        )}
        title="Separate From and To filters"
      >
        <Split className="size-3" />
        From / To
      </button>
      <button
        type="button"
        onClick={() => onChange("any")}
        className={cn(
          "inline-flex h-6 items-center gap-1 border-l border-border px-2 transition-colors",
          isAny ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-card text-muted-foreground hover:bg-muted"
        )}
        title="Show every communication involving selected people"
      >
        <GitMerge className="size-3" />
        Any
      </button>
    </div>
  )
}

function SidePanel({
  title,
  subtitle,
  entities,
  selected,
  onToggle,
  wide,
}: {
  title: string
  subtitle: string
  entities: CellebriteRecord[]
  selected: Set<string>
  onToggle: (entity: CellebriteRecord) => void
  wide?: boolean
}) {
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(0)

  const display = useMemo(() => {
    const needle = search.trim().toLowerCase()
    const keyed = entities
      .map((entity) => ({ entity, key: entityKey(entity), name: entityName(entity) }))
      .filter((row) => row.key)
    const pinned = keyed.filter((row) => selected.has(row.key))
    const pinnedKeys = new Set(pinned.map((row) => row.key))
    const stubs = [...selected]
      .filter((key) => !pinnedKeys.has(key))
      .map((key) => ({
        entity: { key, name: key, _stub: true },
        key,
        name: key,
      }))
    const rest = keyed.filter((row) => {
      if (selected.has(row.key)) return false
      if (!needle) return true
      return `${row.name} ${row.key}`.toLowerCase().includes(needle)
    })
    return [...stubs, ...pinned, ...rest]
  }, [entities, search, selected])

  const pageCount = Math.max(1, Math.ceil(display.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount - 1)
  const start = safePage * PAGE_SIZE
  const visible = display.slice(start, start + PAGE_SIZE)
  const maxHeight = wide ? "max-h-[260px]" : "max-h-[180px]"

  return (
    <div className="flex min-h-0 flex-col">
      <div className="flex items-center gap-2 border-b border-border bg-muted/20 px-3 py-1">
        <span className="text-xs font-semibold">{title}</span>
        <span className="text-[11px] text-muted-foreground">{subtitle}</span>
        <span className="ml-auto text-[11px] text-muted-foreground">
          {compactNumber(selected.size)} selected
        </span>
      </div>
      <div className="flex items-center gap-1 border-b border-border px-2 py-1">
        <Search className="size-3.5 text-muted-foreground" />
        <Input
          value={search}
          onChange={(event) => {
            setSearch(event.target.value)
            setPage(0)
          }}
          placeholder="Search people, numbers, identifiers"
          className="h-7 border-0 bg-transparent px-1 text-xs shadow-none focus-visible:ring-0"
        />
        {search && (
          <Button variant="ghost" size="icon-sm" onClick={() => setSearch("")}>
            <X className="size-3" />
          </Button>
        )}
      </div>
      <div className={cn("min-h-[100px] overflow-y-auto", maxHeight)}>
        {visible.length === 0 ? (
          <div className="px-3 py-4 text-center text-xs text-muted-foreground">
            {search ? "No matching participants." : "No participants indexed."}
          </div>
        ) : (
          visible.map(({ entity, key, name }) => {
            const checked = selected.has(key)
            const count = readNumber(entity, ["message_count", "call_count", "email_count"], 0)
            return (
              <button
                key={key}
                type="button"
                onClick={() => onToggle(entity)}
                className={cn(
                  "flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors",
                  checked ? "bg-amber-500/10 text-foreground" : "text-muted-foreground hover:bg-muted/50"
                )}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  readOnly
                  className="size-3 shrink-0 accent-amber-500"
                  tabIndex={-1}
                />
                {"is_owner" in entity && entity.is_owner ? (
                  <Smartphone className="size-3.5 shrink-0 text-emerald-500" />
                ) : (
                  <UserRound className="size-3.5 shrink-0" />
                )}
                <span className="min-w-0 flex-1 truncate" title={name}>
                  {name}
                </span>
                {count > 0 && <span className="shrink-0 text-[10px]">{compactNumber(count)}</span>}
              </button>
            )
          })
        )}
      </div>
      {pageCount > 1 && (
        <div className="flex items-center gap-1 border-t border-border bg-muted/20 px-2 py-1 text-[11px] text-muted-foreground">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            disabled={safePage === 0}
            onClick={() => setPage((value) => Math.max(0, value - 1))}
          >
            <ChevronLeft className="size-3" />
          </Button>
          <span className="tabular-nums">{safePage + 1} / {pageCount}</span>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            disabled={safePage >= pageCount - 1}
            onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))}
          >
            <ChevronRight className="size-3" />
          </Button>
          <span className="ml-auto">
            {start + 1}-{Math.min(start + PAGE_SIZE, display.length)} of {display.length}
          </span>
        </div>
      )}
    </div>
  )
}

function SelectedChip({
  participant,
  modeIsAny,
  onRemove,
}: {
  participant: ParticipantFilter
  modeIsAny: boolean
  onRemove: () => void
}) {
  const label = modeIsAny
    ? "Any"
    : participant.role === "from"
      ? "From"
      : participant.role === "to"
        ? "To"
        : "Any"
  return (
    <span
      className={cn(
        "inline-flex max-w-[220px] items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]",
        modeIsAny
          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
          : participant.role === "from"
            ? "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300"
            : participant.role === "to"
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
              : "border-border bg-muted text-muted-foreground"
      )}
    >
      <span className="shrink-0 text-[9px] uppercase tracking-wide opacity-70">{label}</span>
      <span className="truncate" title={participant.name}>{participant.name}</span>
      <button type="button" onClick={onRemove} className="ml-0.5 rounded hover:opacity-70">
        <X className="size-3" />
      </button>
    </span>
  )
}
