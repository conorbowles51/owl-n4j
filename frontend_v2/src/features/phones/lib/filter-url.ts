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
}

export const DEFAULT_VIEW: ConversationView = {
  tab: "threads", thread: null, record: null, people: [], mode: "involving", expand: false, phones: [], from: null,
  to: null, kinds: [], apps: [], directions: [], deleted: null, unreadable: null, attachment: null, text: "",
  exact: false, everyCopy: false, allChannels: false, sort: "oldest_first", threadSort: "recent", zone: "case",
  names: "phone",
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
  set("deleted", triWord(v.deleted))
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
export function viewToFilter(caseId: string, v: ConversationView, zoneName: string, withThread = true): StreamFilter {
  const f: StreamFilter = { case_id: caseId, zone: { mode: v.zone, phone: v.zone === "phone" && v.phones.length === 1 ? v.phones[0] : null } }
  if (v.phones.length) f.phones = v.phones
  if (withThread && v.thread && v.tab === "threads") f.threads = [v.thread]
  const between = v.mode === "between" && v.people.length === 2
  if (v.people.length) {
    f.participants = v.people
    // Between needs exactly two people; with one or three it reads as Involving, never as no people filter at all.
    f.participant_mode = v.mode === "between" && !between ? "any" : MODE[v.mode]
    if (v.expand) f.expand_person_identities = true
    // "All channels" (07 J-3) takes in group chats with both people as well as their direct messages.
    if (between) f.group_scope = v.allChannels ? "include_groups" : "direct"
  }
  if (v.kinds.length) f.kinds = v.kinds as StreamFilter["kinds"]
  if (v.apps.length) f.apps = v.apps
  if (v.directions.length) f.directions = v.directions as StreamFilter["directions"]
  // The report's deletion states (live 2 November: Intact, Unknown, Trash, Deleted, or none recorded).
  if (v.deleted !== null) f.deleted_states = v.deleted ? ["Deleted", "Trash"] : [null, "Intact", "Unknown"]
  const flags: NonNullable<StreamFilter["flags"]> = {}
  if (v.unreadable !== null) flags.unreadable = v.unreadable
  if (v.attachment !== null) flags.has_attachment = v.attachment
  if (Object.keys(flags).length) f.flags = flags
  if (v.from) f.from_instant = new Date(dayStart(v.from, zoneName)).toISOString()
  if (v.to) {
    const next = new Date(Date.UTC(Number(v.to.slice(0, 4)), Number(v.to.slice(5, 7)) - 1, Number(v.to.slice(8, 10)) + 1))
    f.to_instant = new Date(dayStart(next.toISOString().slice(0, 10), zoneName) - 1).toISOString()
  }
  if (v.text.trim()) f.text = { query: v.text.trim(), exact_characters: v.exact }
  if (v.everyCopy) f.collapse_copies = false
  f.names = { mode: v.names }
  if (v.sort !== "oldest_first") f.sort = v.sort
  return f
}
