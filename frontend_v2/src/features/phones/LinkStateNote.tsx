import { useState } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { ReplacedLinkNote } from "./ReplacedLinkNote"
import type { LinkState, LinkStateList } from "./link-states"

const n = (v: number) => v.toLocaleString("en-US")

function Lines({ heading, list, whole }: { heading: string; list: LinkStateList; whole: number }) {
  const ofWhole = whole > 1 ? ` (${n(list.records)} of ${n(whole)} records)` : ""
  return (
    <div>
      <p className="font-medium">{heading}{ofWhole}</p>
      {list.items.map((i) => <p key={`${i.record_uid}:${i.field}`}>{i.words}</p>)}
      {list.clipped && <p>The first {n(list.items.length)} of {n(list.count)} changes are listed here; the export lists all of them.</p>}
    </div>
  )
}

/**
 * 07 section 6.3: what happened to a linked record since it was collected. Corrected shows both values; reading changed
 * says who changed it and when, and offers Keep or Remove to the person who added the link. The stored link never
 * changes; the state is worked out on the server each time the link is shown.
 */
export function LinkStateNote({ caseId, state, onChoose, busy }: {
  caseId: string
  state: LinkState | undefined
  onChoose?: (state: LinkState, choice: "keep" | "remove") => Promise<unknown>
  busy?: boolean
}) {
  const [error, setError] = useState<string | null>(null)
  if (!state) return null
  const { corrected, reading_changed: reading, set_aside: aside, reread, kept } = state
  const choose = async (choice: "keep" | "remove") => {
    setError(null)
    try {
      await onChoose?.(state, choice)
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "Your choice was not saved.")
    }
  }
  return (
    <div className="space-y-1 text-[10px] text-muted-foreground" data-testid="link-state-note">
      <ReplacedLinkNote caseId={caseId} state={state.replaced ?? undefined} />
      {corrected.count > 0 && <Lines heading="Corrected since collected" list={corrected} whole={state.records} />}
      {reading.count > 0 && <Lines heading="Reading changed since collected" list={reading} whole={state.records} />}
      {aside && (
        <p>{aside.words} <Link className="underline" to={`/cases/${encodeURIComponent(caseId)}/records/${encodeURIComponent(aside.shown_record_uid)}`}>Open the record shown</Link></p>
      )}
      {reread && <p>{reread.words}</p>}
      {kept && <p>{kept.words}</p>}
      {state.needs_choice && !state.can_choose && state.added_by && <p>Keep or Remove is for {state.added_by}, who added this link.</p>}
      {state.can_choose && onChoose && (
        <span className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void choose("keep")}>Keep</Button>
          {state.can_remove
            ? <Button size="sm" variant="outline" disabled={busy} onClick={() => void choose("remove")}>Remove</Button>
            : <span>To remove it, remove this assessment.</span>}
        </span>
      )}
      {error && <p role="alert" className="text-destructive">{error}</p>}
    </div>
  )
}
