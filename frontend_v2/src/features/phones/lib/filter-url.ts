import { dayStart } from "@/lib/evidence-time"
import type { StreamFilter, ThreadSort } from "../api"

/**
 * The Conversations view in the URL (03 section 6.4: every filter is in the URL, so any view is linkable and Back
 * returns to it). Ids only; names are looked up again on load. Parameter names follow 07 section 4.13 and the links
 * Workspace stores (`thread`, `record`, `phones`, `people`).
 */

export type Mode = "involving" | "between" | "sent-by" | "sent-to"
export type Tab = "threads" | "people"
export type Tri = boolean | null
/** One deletion state alone; `deleted` keeps "deleted or in trash" (the links the Phone summary writes). */
export type OneDeletion = "Deleted" | "Trash" | null

/** The `apps` value that means "the report names no app": about one event in six on the reference phones. */
export const NO_APP = "not-recorded"

export interface ConversationView {
  tab: Tab
  thread: string | null
  record: string | null
  people: string[]
  mode: Mode
  expand: boolean
  phones: string[]
  from: string | null
  to: string | null
  kinds: string[]
  apps: string[]
  directions: string[]
  deleted: Tri
  oneDeletion: OneDeletion
  unreadable: Tri
  attachment: Tri
  text: string
  exact: boolean
  everyCopy: boolean
  allChannels: boolean
  sort: "oldest_first" | "newest_first"
  threadSort: ThreadSort
  zone: "phone" | "case" | "utc"
  names: "phone" | "case"
  /** A search's text marked in the list without filtering it (03 S-8), and the message to open at. */
  hl: string
  hlExact: boolean
  at: string | null
  /** A saved selection opened from a link: only its frozen records. */
  selection: string | null
  /** False: only records with a time (?notime=0), as a crossing that names days opens them (07 XF-1, XF-4). */
  noTime: boolean
  /** The Significant layer's toggle (07 XF-11): only events with a significant phone identity. */
  significant: boolean
}

export const DEFAULT_VIEW: ConversationView = {
  tab: "threads", thread: null, record: null, people: [], mode: "involving", expand: false, phones: [], from: null,
  to: null, kinds: [], apps: [], directions: [], deleted: null, oneDeletion: null, unreadable: null, attachment: null, text: "",
  exact: false, everyCopy: false, allChannels: false, sort: "oldest_first", threadSort: "recent", zone: "case",
  names: "phone", hl: "", hlExact: false, at: null, selection: null, noTime: true, significant: false,
}

const list = (q: URLSearchParams, k: string) => (q.get(k) ? q.get(k)!.split(",").filter(Boolean) : [])
const tri = (v: string | null): Tri => (v === "only" ? true : v === "exclude" ? false : null)
const triWord = (v: Tri) => (v === true ? "only" : v === false ? "exclude" : null)

export function viewFromSearch(search: string, fixedPhone?: string | null): ConversationView {
  const q = new URLSearchParams(search)
  const pick = <T extends string>(k: string, allowed: readonly T[], fallback: T): T =>
    (allowed as readonly string[]).includes(q.get(k) ?? "") ? (q.get(k) as T) : fallback
  const people = list(q, "people")
  return {
    tab: pick("tab", ["threads", "people"] as const, people.length ? "people" : "threads"),
    thread: q.get("thread"),
    record: q.get("record"),
    people,
    mode: pick("mode", ["involving", "between", "sent-by", "sent-to"] as const, "involving"),
    expand: q.get("expand") === "1",
    phones: fixedPhone ? [fixedPhone] : list(q, "phones"),
    from: q.get("from"),
    to: q.get("to"),
    kinds: list(q, "kinds"),
    apps: list(q, "apps"),
    directions: list(q, "directions"),
    deleted: tri(q.get("deleted")),
    oneDeletion: q.get("deleted") === "deleted" ? "Deleted" : q.get("deleted") === "trash" ? "Trash" : null,
    unreadable: tri(q.get("unreadable")),
    attachment: tri(q.get("attachment")),
    text: q.get("q") ?? "",
    exact: q.get("exact") === "1",
    everyCopy: q.get("copies") === "all",
    allChannels: q.get("channels") === "all",
    sort: pick("sort", ["oldest_first", "newest_first"] as const, "oldest_first"),
    threadSort: pick("threads", ["recent", "first", "volume", "unreviewed", "name"] as const, "recent"),
    zone: pick("zone", ["phone", "case", "utc"] as const, "case"),
    names: pick("names", ["phone", "case"] as const, "phone"),
    hl: q.get("hl") ?? "",
    hlExact: q.get("hlexact") === "1",
    at: q.get("at"),
    selection: q.get("selection"),
    noTime: q.get("notime") !== "0",
    significant: q.get("significant") === "1",
  }
}

export function viewToSearch(v: ConversationView, fixedPhone?: string | null): string {
  const q = new URLSearchParams()
  const set = (k: string, val: string | null | undefined, skip?: string) => {
    if (val && val !== skip) q.set(k, val)
  }
  set("tab", v.tab, v.people.length ? "people" : "threads")
  set("thread", v.thread)
  set("record", v.record)
  set("people", v.people.join(","))
  set("mode", v.mode, "involving")
  set("expand", v.expand ? "1" : null)
  if (!fixedPhone) set("phones", v.phones.join(","))
  set("from", v.from)
  set("to", v.to)
  set("kinds", v.kinds.join(","))
  set("apps", v.apps.join(","))
  set("directions", v.directions.join(","))
  set("deleted", v.oneDeletion ? v.oneDeletion.toLowerCase() : triWord(v.deleted))
  set("unreadable", triWord(v.unreadable))
  set("attachment", triWord(v.attachment))
  set("q", v.text.trim())
  set("exact", v.exact ? "1" : null)
  set("copies", v.everyCopy ? "all" : null)
  set("channels", v.allChannels ? "all" : null)
  set("sort", v.sort, "oldest_first")
  set("threads", v.threadSort, "recent")
  set("zone", v.zone, "case")
  set("names", v.names, "phone")
  set("hl", v.hl.trim())
  set("hlexact", v.hlExact ? "1" : null)
  set("at", v.at)
  set("selection", v.selection)
  set("notime", v.noTime ? null : "0")
  set("significant", v.significant ? "1" : null)
  return q.toString()
}

const MODE: Record<Mode, StreamFilter["participant_mode"]> = {
  involving: "any",
  between: "between",
  "sent-by": "sent_by",
  "sent-to": "sent_to",
}

/**
 * The stream filter of a view. `withThread` false gives the filter of the thread list (6.3 ignores the thread).
 * Dates are days in the display zone: from the start of `from` to the end of `to` (4.3).
 */
/** The participant key the server reads as "the owner of each phone in scope" (streams.PHONE_OWNER). */
export const PHONE_OWNER = "owner:this-phone"

/** The zone a view's dates are days in. */
export function dayZoneOf(v: ConversationView, zoneName: string): string {
  return v.zone === "utc" ? "UTC" : zoneName
}

export function viewToFilter(caseId: string, v: ConversationView, zoneName: string, withThread = true): StreamFilter {
  const f: StreamFilter = { case_id: caseId, zone: { mode: v.zone, phone: v.zone === "phone" && v.phones.length === 1 ? v.phones[0] : null } }
  if (v.phones.length) f.phones = v.phones
  if (v.selection) f.selection = v.selection
  if (withThread && v.thread && v.tab === "threads") f.threads = [v.thread]
  // Between A and B: B is the second person, or with one person the owner of each phone (07 J-3)
  const between = v.mode === "between" && (v.people.length === 2 || v.people.length === 1)
  if (v.people.length) {
    f.participants = between && v.people.length === 1 ? [...v.people, PHONE_OWNER] : v.people
    // Between needs one or two people; with three it reads as Involving, never as no people filter at all.
    f.participant_mode = v.mode === "between" && !between ? "any" : MODE[v.mode]
    if (v.expand) f.expand_person_identities = true
    // "All channels" (07 J-3) takes in group chats with both people as well as their direct messages.
    if (between) f.group_scope = v.allChannels ? "include_groups" : "direct"
  }
  if (v.kinds.length) f.kinds = v.kinds as StreamFilter["kinds"]
  if (v.apps.length) f.apps = v.apps.map((a) => (a === NO_APP ? null : a))
  if (v.directions.length) f.directions = v.directions as StreamFilter["directions"]
  // The report's deletion states (live 2 November: Intact, Unknown, Trash, Deleted, or none recorded).
  if (v.oneDeletion) f.deleted_states = [v.oneDeletion]
  else if (v.deleted !== null) f.deleted_states = v.deleted ? ["Deleted", "Trash"] : [null, "Intact", "Unknown"]
  const flags: NonNullable<StreamFilter["flags"]> = {}
  if (v.unreadable !== null) flags.unreadable = v.unreadable
  if (v.attachment !== null) flags.has_attachment = v.attachment
  if (Object.keys(flags).length) f.flags = flags
  if (!v.noTime) f.include_no_time = false
  if (v.significant) f.significant_only = true
  // a view in UTC has its days in UTC, whatever the case's zone (a volume chart's week is counted in UTC)
  const dayZone = dayZoneOf(v, zoneName)
  if (v.from) f.from_instant = new Date(dayStart(v.from, dayZone)).toISOString()
  if (v.to) {
    const next = new Date(Date.UTC(Number(v.to.slice(0, 4)), Number(v.to.slice(5, 7)) - 1, Number(v.to.slice(8, 10)) + 1))
    f.to_instant = new Date(dayStart(next.toISOString().slice(0, 10), dayZone) - 1).toISOString()
  }
  if (v.text.trim()) f.text = { query: v.text.trim(), exact_characters: v.exact }
  if (v.everyCopy) f.collapse_copies = false
  f.names = { mode: v.names }
  if (v.sort !== "oldest_first") f.sort = v.sort
  return f
}

const DIRECTION_WORDS: Record<string, string> = { incoming: "Incoming", outgoing: "Outgoing", unknown: "Direction unknown" }

export interface FilterChip {
  key: string
  text: string
  clear: Partial<ConversationView>
}

/** What the view narrows by beyond people, phones and kinds (the scope bar's own chips), in words, each removable. */
export function filterChips(v: ConversationView): FilterChip[] {
  const out: FilterChip[] = []
  for (const a of v.apps) out.push({ key: `app:${a}`, text: a === NO_APP ? "App not recorded" : a, clear: { apps: v.apps.filter((x) => x !== a) } })
  for (const d of v.directions) out.push({ key: `dir:${d}`, text: DIRECTION_WORDS[d] ?? d, clear: { directions: v.directions.filter((x) => x !== d) } })
  // both dates are one chip in the scope bar; one date alone is a chip here, or it would narrow the list unseen
  if (v.from && !v.to) out.push({ key: "from", text: `From ${v.from}`, clear: { from: null } })
  if (v.to && !v.from) out.push({ key: "to", text: `Up to ${v.to}`, clear: { to: null } })
  if (v.oneDeletion) out.push({ key: "deleted", text: v.oneDeletion === "Deleted" ? "Deleted only" : "In trash only", clear: { oneDeletion: null } })
  else if (v.deleted !== null) out.push({ key: "deleted", text: v.deleted ? "Deleted or in trash only" : "Without deleted or in trash", clear: { deleted: null } })
  if (v.unreadable !== null) out.push({ key: "unreadable", text: v.unreadable ? "Unreadable only" : "Without unreadable", clear: { unreadable: null } })
  if (v.attachment !== null) out.push({ key: "attachment", text: v.attachment ? "Has an attachment" : "No attachment", clear: { attachment: null } })
  if (v.text.trim()) out.push({ key: "text", text: `Contains "${v.text.trim()}"${v.exact ? ", exact characters" : ""}`, clear: { text: "", exact: false } })
  if (!v.noTime) out.push({ key: "notime", text: "Only those with a time", clear: { noTime: true } })
  return out
}

/** Every narrowing the filter bar sets, cleared at once. People, phones and the open thread are left alone. */
export const NO_FILTERS: Partial<ConversationView> = {
  from: null, to: null, kinds: [], apps: [], directions: [], deleted: null, oneDeletion: null, unreadable: null, attachment: null, text: "", exact: false, noTime: true,
}

export function hasFilters(v: ConversationView): boolean {
  return filterChips(v).length > 0 || v.kinds.length > 0 || !!(v.from && v.to)
}

/** The chips here in words: what the scope bar's own words (window, kinds) leave out. */
export function filterChipWords(v: ConversationView): string {
  return filterChips(v).map((c) => c.text).join(", ")
}

/** The whole narrowing in words, for what a person keeps or sends on: a copy's footer, an export, a saved view. */
export function filterWordsOf(v: ConversationView): string {
  const window = v.from && v.to ? [`${v.from} to ${v.to}`] : []
  return [...window, ...v.kinds, ...filterChips(v).map((c) => c.text)].join(", ")
}
