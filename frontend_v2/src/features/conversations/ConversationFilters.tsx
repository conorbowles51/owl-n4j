import { useQuery } from "@tanstack/react-query"
import { useEffect, useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { failureText, streamApps, streamIndex, type StreamFilter } from "@/features/phones/api"
import { filterChips, hasFilters, NO_APP, NO_FILTERS, type ConversationView, type Tri } from "@/features/phones/lib/filter-url"
import { fmt } from "@/features/phones/ui/count-sentence"
import { Chip } from "@/features/phones/ui/ScopeBar"

/**
 * The Conversations filter bar (03 section 6.4). Every control writes the view, so each filter is in the URL, a
 * removable chip and a server filter; the count under it is the server's exact total over every conversation in
 * scope. Nothing is hidden until a person chooses: deleted and unreadable messages are listed by default.
 */

const KINDS = [["message", "Messages"], ["call", "Calls"], ["email", "Emails"], ["voicemail", "Voicemail"], ["chat_activity", "Group activity"]] as const
const DIRECTIONS = [["incoming", "Incoming"], ["outgoing", "Outgoing"], ["unknown", "Unknown"]] as const
const TEXT_WAIT_MS = 500

type SetView = (patch: Partial<ConversationView> | ((v: ConversationView) => Partial<ConversationView>), replace?: boolean) => void

const toggled = (list: string[], value: string, on: boolean) => (on ? [...list.filter((x) => x !== value), value] : list.filter((x) => x !== value))

function Pick({ label, count, children, onOpen }: { label: string; count: number; children: React.ReactNode; onOpen?: () => void }) {
  return (
    <Popover onOpenChange={(open) => open && onOpen?.()}>
      <PopoverTrigger asChild>
        <Button size="sm" variant={count ? "secondary" : "outline"}>
          {label}
          {count ? ` (${fmt(count)})` : ""}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="flex max-h-80 w-64 flex-col gap-1 overflow-auto p-2 text-sm">
        {children}
      </PopoverContent>
    </Popover>
  )
}

function Checks({ options, chosen, onChange }: { options: readonly (readonly [string, string])[]; chosen: string[]; onChange: (value: string, on: boolean) => void }) {
  return (
    <>
      {options.map(([value, words]) => (
        <label key={value} className="flex items-center gap-2">
          <input type="checkbox" checked={chosen.includes(value)} onChange={(e) => onChange(value, e.target.checked)} />
          <span className="min-w-0 flex-1 truncate">{words}</span>
        </label>
      ))}
    </>
  )
}

function TriPick({ label, only, without, value, onChange }: { label: string; only: string; without: string; value: Tri; onChange: (v: Tri) => void }) {
  return (
    <label className="flex items-center justify-between gap-2">
      {label}
      <select className="rounded border bg-card px-1 py-0.5" value={value === null ? "any" : value ? "only" : "exclude"}
        onChange={(e) => onChange(e.target.value === "any" ? null : e.target.value === "only")}>
        <option value="any">Any</option>
        <option value="only">{only}</option>
        <option value="exclude">{without}</option>
      </select>
    </label>
  )
}

export function ConversationFilters({ view, setView, listFilter, zoneWords, threadCounts, phones }: {
  view: ConversationView
  setView: SetView
  /** The view's filter over every conversation in scope (no open thread). */
  listFilter: StreamFilter
  zoneWords: string
  threadCounts?: { threads?: number; threads_total?: number }
  /** Offered when the page is not fixed to one phone. */
  phones?: { id: string; label: string }[]
}) {
  const [appsOpen, setAppsOpen] = useState(false)
  const apps = useQuery({ queryKey: ["phone-stream-apps", listFilter], queryFn: () => streamApps(listFilter), enabled: appsOpen })
  const narrowed = hasFilters(view)
  const total = useQuery({ queryKey: ["phone-stream-total", listFilter], queryFn: () => streamIndex(listFilter), enabled: narrowed })
  const chips = useMemo(() => filterChips(view), [view])

  // A filter is asked for when the typing stops: each ask is a search on the server and a line in the review record.
  const [text, setText] = useState(view.text)
  const [seen, setSeen] = useState(view.text)
  if (view.text !== seen) {
    setSeen(view.text)
    setText(view.text)
  }
  useEffect(() => {
    if (text.trim() === view.text.trim()) return undefined
    const t = setTimeout(() => setView({ text: text.trim() }, true), TEXT_WAIT_MS)
    return () => clearTimeout(t)
  }, [text, view.text, setView])

  const [dateNote, setDateNote] = useState<string | null>(null)
  const setDay = (field: "from" | "to", day: string) => {
    const next = { from: view.from, to: view.to, [field]: day || null } // the dates shown beside the control
    if (next.from && next.to && next.from > next.to) {
      setDateNote("The start is after the end, so that date was not applied.")
      return
    }
    setDateNote(null)
    setView({ [field]: day || null })
  }

  const deletion = view.oneDeletion ?? (view.deleted === true ? "both" : view.deleted === false ? "exclude" : "any")
  const stateCount = (deletion !== "any" ? 1 : 0) + (view.unreadable !== null ? 1 : 0)
  const dated = !!(view.from || view.to)
  return (
    <div className="flex flex-col gap-1" data-testid="conversation-filters">
      <div className="flex flex-wrap items-center gap-1.5 text-sm">
        {phones && phones.length > 1 && (
          <Pick label="Phones" count={view.phones.length}>
            <Checks options={phones.map((p) => [p.id, p.label] as const)} chosen={view.phones} onChange={(x, on) => setView((v) => ({ phones: toggled(v.phones, x, on) }))} />
          </Pick>
        )}
        <Pick label="Apps" count={view.apps.length} onOpen={() => setAppsOpen(true)}>
          {apps.isLoading && <p role="status">Counting the apps in scope</p>}
          {apps.isError && <p role="alert">{failureText(apps.error, "The apps could not be listed.")}</p>}
          {apps.data && (
            <Checks
              options={[
                ...apps.data.items.map((a) => [a.app ?? NO_APP, `${a.app ?? "App not recorded"} (${fmt(a.count)})`] as const),
                ...view.apps.filter((a) => !apps.data.items.some((i) => (i.app ?? NO_APP) === a)).map((a) => [a, `${a === NO_APP ? "App not recorded" : a} (0)`] as const),
              ]}
              chosen={view.apps}
              onChange={(x, on) => setView((v) => ({ apps: toggled(v.apps, x, on) }))}
            />
          )}
        </Pick>
        <Pick label="Kinds" count={view.kinds.length}>
          <Checks options={KINDS} chosen={view.kinds} onChange={(x, on) => setView((v) => ({ kinds: toggled(v.kinds, x, on) }))} />
        </Pick>
        <Pick label="Direction" count={view.directions.length}>
          <Checks options={DIRECTIONS} chosen={view.directions} onChange={(x, on) => setView((v) => ({ directions: toggled(v.directions, x, on) }))} />
        </Pick>
        <Pick label="State" count={stateCount}>
          <label className="flex items-center justify-between gap-2">
            Deleted
            <select aria-label="Deleted" className="rounded border bg-card px-1 py-0.5" value={deletion}
              onChange={(e) => {
                const v = e.target.value
                setView({ deleted: v === "both" ? true : v === "exclude" ? false : null, oneDeletion: v === "Deleted" || v === "Trash" ? v : null })
              }}>
              <option value="any">Any</option>
              <option value="both">Deleted or in trash</option>
              <option value="Deleted">Deleted only</option>
              <option value="Trash">In trash only</option>
              <option value="exclude">Leave them out</option>
            </select>
          </label>
          <TriPick label="Unreadable" only="Only these" without="Leave them out" value={view.unreadable} onChange={(v) => setView({ unreadable: v })} />
          <p className="text-xs text-muted-foreground">Nothing is left out until you choose.</p>
        </Pick>
        <label className="inline-flex items-center gap-1">
          Attachment
          <select className="rounded border bg-card px-1 py-0.5" value={view.attachment === null ? "any" : view.attachment ? "only" : "exclude"}
            onChange={(e) => setView({ attachment: e.target.value === "any" ? null : e.target.value === "only" })}>
            <option value="any">Any</option>
            <option value="only">Has an attachment</option>
            <option value="exclude">No attachment</option>
          </select>
        </label>
        <label className="inline-flex items-center gap-1">
          From
          <input type="date" className="rounded border bg-background px-1 py-0.5" value={view.from ?? ""} max={view.to ?? undefined} onChange={(e) => setDay("from", e.target.value)} />
        </label>
        <label className="inline-flex items-center gap-1">
          To
          <input type="date" className="rounded border bg-background px-1 py-0.5" value={view.to ?? ""} min={view.from ?? undefined} onChange={(e) => setDay("to", e.target.value)} />
        </label>
        <span className="text-xs text-muted-foreground" data-testid="filter-zone">Days in {zoneWords}</span>
        <label className="inline-flex items-center gap-1">
          <span className="sr-only">Contains</span>
          <input type="search" className="w-44 rounded border bg-background px-2 py-0.5" placeholder="Contains these words" value={text} onChange={(e) => setText(e.target.value)} />
        </label>
        <label className="inline-flex items-center gap-1 text-xs">
          <input type="checkbox" checked={view.exact} onChange={(e) => setView({ exact: e.target.checked })} />
          Exact characters
        </label>
      </div>
      {dateNote && <p role="alert" className="text-xs">{dateNote}</p>}
      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5" data-testid="filter-chips">
          {chips.map((c) => (
            <Chip key={c.key} text={c.text} onRemove={() => setView(c.clear)} />
          ))}
        </div>
      )}
      {narrowed && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <p role="status" data-testid="filter-total">
            {total.isError
              ? failureText(total.error, "The matching messages could not be counted.")
              : total.data && threadCounts?.threads !== undefined
                ? `${fmt(total.data.counts.events ?? 0)} ${total.data.counts.events === 1 ? "message or call matches" : "messages and calls match"} in ${fmt(threadCounts.threads)} of ${fmt(threadCounts.threads_total ?? threadCounts.threads)} conversations.`
                : "Counting the matches"}
          </p>
          {dated && view.noTime && !!total.data?.no_time_count && (
            <p className="text-xs">
              {fmt(total.data.no_time_count)} with no time {total.data.no_time_count === 1 ? "is" : "are"} included, as they cannot be placed on a day.{" "}
              <button type="button" className="underline underline-offset-2" onClick={() => setView({ noTime: false })}>
                Leave them out
              </button>
            </p>
          )}
          <Button size="sm" variant="ghost" onClick={() => setView(NO_FILTERS)}>
            Clear filters
          </Button>
        </div>
      )}
    </div>
  )
}
