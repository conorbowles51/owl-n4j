import { useState } from "react"
import { Button } from "@/components/ui/button"
import type { RelationMember } from "@/features/relations/api"
import { corroborateAPI, type GroupBy, type Grouped, type ItemGroup } from "./api"
import { eachRuns, MAX_EACH } from "./group-runs"

const BY_WORDS: Record<GroupBy, string> = { person: "Person", day: "Day", place: "Place", amount: "Amount", app: "App" }

/**
 * Group the selection (lx-corrorest C): by person, day, place, amount or app. Each group states its whole count. Pick one
 * group to ask about alone (against the others), or ask every group against the others. What cannot be placed in a
 * group is counted and named, never dropped.
 */
export function GroupPicker({ caseId, members, busy, onGroup, onEach }: {
  caseId: string
  members: RelationMember[]
  busy: boolean
  onGroup: (g: ItemGroup, all: ItemGroup[]) => void
  onEach: (runs: ItemGroup[], all: ItemGroup[]) => void
}) {
  const [by, setBy] = useState<GroupBy | "">("")
  const [got, setGot] = useState<Grouped | null>(null)
  const [reading, setReading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pick = async (next: GroupBy | "") => {
    setBy(next)
    setGot(null)
    setError(null)
    if (!next) return
    setReading(true)
    try {
      setGot(await corroborateAPI.group(caseId, members, next))
    } catch (e) {
      setError(e instanceof Error ? e.message : "The selection could not be grouped. Nothing was changed.")
    } finally {
      setReading(false)
    }
  }
  const each = got ? eachRuns(got.groups) : null
  return (
    <details className="rounded border px-2 py-1 text-sm">
      <summary className="cursor-pointer font-medium">Group these{got ? `: ${got.group_count.toLocaleString("en-US")} by ${BY_WORDS[got.by].toLowerCase()}` : ""}</summary>
      <label className="mt-1 flex flex-col text-xs text-muted-foreground">Group by
        <select className="rounded border bg-card px-2 py-1 text-sm text-foreground" value={by} onChange={(e) => void pick(e.target.value as GroupBy | "")}>
          <option value="">Not grouped</option>
          {(Object.keys(BY_WORDS) as GroupBy[]).map((k) => <option key={k} value={k}>{BY_WORDS[k]}</option>)}
        </select>
      </label>
      {reading && <p role="status" className="text-xs">Grouping {members.length.toLocaleString("en-US")} items…</p>}
      {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
      {got && (
        <div className="mt-1 flex flex-col gap-1 text-xs">
          {got.groups.length === 0 && <p>No item could be placed in a group by {BY_WORDS[got.by].toLowerCase()}.</p>}
          <ul className="flex max-h-48 flex-col gap-1 overflow-y-auto">
            {got.groups.map((g) => (
              <li key={g.key} className="flex flex-wrap items-center gap-2">
                <span>{g.label} <span className="text-muted-foreground">· {g.count.toLocaleString("en-US")} {g.count === 1 ? "item" : "items"}</span></span>
                <Button size="sm" variant="outline" disabled={busy || g.people.length === 0} onClick={() => onGroup(g, got.groups)}
                  title={g.people.length === 0 ? "No person is named in this group, so there is no one to compare with." : "Ask about this group against the others"}>Ask about this group</Button>
              </li>
            ))}
          </ul>
          {got.clipped > 0 && <p role="status">{got.clipped.toLocaleString("en-US")} more groups are not listed. Narrow the selection or the scope to see them.</p>}
          {got.in_several_groups > 0 && <p>{got.in_several_groups.toLocaleString("en-US")} items name more than one {BY_WORDS[got.by].toLowerCase()} and are in each of their groups.</p>}
          {got.left_out.map((l) => <p key={l.why} role="status">{l.count.toLocaleString("en-US")} items are in no group: each {l.why}.</p>)}
          {got.unread > 0 && <p role="status">{got.unread.toLocaleString("en-US")} chosen items could not be read by Corroborate and are not grouped.</p>}
          {each && each.runs.length > 1 && (
            <div>
              <Button size="sm" disabled={busy} onClick={() => onEach(each.runs, got.groups)}>Each group against the others ({each.runs.length} runs)</Button>
              {each.skipped > 0 && <p role="status">Only the {MAX_EACH} biggest groups are run; {each.skipped} smaller ones are not.</p>}
              {each.withoutPeople > 0 && <p role="status">{each.withoutPeople} groups name no person, so they have no one to compare with and are not run.</p>}
            </div>
          )}
        </div>
      )}
    </details>
  )
}
