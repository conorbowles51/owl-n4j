import { useState } from "react"
import { useInRouterContext, useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { SURFACE_WORDS, type GroupInput, type ItemInput, type Surface } from "@/features/theory/api"
import { useSwitch } from "@/lib/ui-switches"
import { openCorroborate } from "@/features/leads/open"
import { currentQuery, relationAPI, setCurrentQuery, skippedWords, toMembers } from "./api"

const TYPE_WORDS: Record<string, string> = {
  evidence_passage: "document passages", interview: "interviews", agent_answer: "assistant answers", dossier: "dossiers",
  phone_file: "phone files", phone_thread: "phone threads", phone_identity: "phone identities", phone_extraction: "phone extractions",
  phone_analysis: "phone analyses", phone_selection: "phone selections", phone_view: "phone views", statement_check: "statement checks",
  history_step: "steps", agent_artifact: "assistant work", task: "tasks", deadline: "deadlines", witness: "witnesses",
}

export interface LookIntoProps {
  caseId: string
  surface: Surface
  items?: ItemInput[]
  group?: GroupInput
  size?: "sm" | "default"
  label?: string
}

/**
 * "Corroborate" (lx-overlaps D): next to Add to theory on every surface. It saves what is chosen as one
 * group, starts the analysis, and opens the result. A look already in progress can be added to, so a payment, a
 * passage, a phone meeting and a graph entity from different screens form one group. Items the analysis cannot read are
 * named, never dropped without a word.
 */
export function LookIntoButton(props: LookIntoProps) {
  const inRouter = useInRouterContext()
  const v2 = useSwitch("corroborate-v2")
  // Outside a router (a story, a unit test of a screen part) there is nowhere to open the result, so there is no button.
  if (!inRouter) return null
  return v2 ? <CorroborateButton {...props} /> : <LookIntoClassic {...props} />
}

/** Corroborate v2 (lx-corroselect): the choice joins the case-wide selection, and the question menu opens on all of it. */
function CorroborateButton({ caseId, surface, items, group, size = "sm" }: LookIntoProps) {
  const converted = toMembers(items, group)
  const total = group ? group.members.length : (items?.length ?? 0)
  const first = items?.[0]?.target_label
  // lx-leads C: one action on any selection; the Corroborate panel opens over this page
  const go = () => openCorroborate({
    caseId,
    screen: SURFACE_WORDS[surface],
    label: group ? group.words : total === 1 && first ? first : `${total.toLocaleString("en-US")} items`,
    members: converted.members,
    skipped: converted.skipped,
  })
  return (
    <Button size={size} variant="outline" disabled={total === 0 || converted.members.length === 0} onClick={go}
      disabledReason={total === 0 ? "Nothing is selected" : skippedWords(converted.skipped, true)}
      title={total === 0 ? "Nothing is selected" : converted.members.length === 0 ? skippedWords(converted.skipped, true) : "Corroborate this: the leads already here, or a new question"}>
      Corroborate
    </Button>
  )
}

function LookIntoClassic({ caseId, surface, items, group, size = "sm", label = "Corroborate" }: LookIntoProps) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()
  const converted = toMembers(items, group)
  const total = group ? group.members.length : (items?.length ?? 0)
  const current = open ? currentQuery(caseId) : null
  const go = async (extend: boolean) => {
    setBusy(true)
    setError(null)
    try {
      const made = await relationAPI.create(caseId, { members: converted.members, surface, ...(extend && current ? { extends: current.id } : {}) })
      setCurrentQuery(caseId, { id: made.group.id, count: made.group.member_count })
      setOpen(false)
      navigate(`/cases/${caseId}/relations/${made.group.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : "The look could not be started. Nothing was saved.")
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <Button size={size} variant="outline" disabled={total === 0} onClick={() => setOpen(true)}
        title={total === 0 ? "Nothing is selected" : "Mark these as possibly related and see how the records could link them"}>
        {label}
      </Button>
      {open && (
        <Dialog open onOpenChange={(o) => !o && !busy && setOpen(false)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Corroborate</DialogTitle>
              <DialogDescription>
                Loupe runs every analysis that applies to the items and lists how they could be linked and where nothing links them.
                The records show what occurs together, not why.
              </DialogDescription>
            </DialogHeader>
            <p className="text-sm">
              {converted.members.length} of {total} chosen {total === 1 ? "item" : "items"} can be compared.
              {converted.skipped.length > 0 && (
                <> Not compared yet: {converted.skipped.map((s) => `${s.count} ${TYPE_WORDS[s.type] ?? s.type.replace(/_/g, " ")}`).join(", ")}.</>
              )}
            </p>
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <DialogFooter className="gap-2">
              {current && (
                <Button disabled={busy || converted.members.length === 0} onClick={() => void go(true)}>
                  Add to the look in progress ({current.count} items)
                </Button>
              )}
              <Button variant={current ? "outline" : "primary"} disabled={busy || converted.members.length === 0} onClick={() => void go(false)}>
                {busy ? "Starting…" : "Start a new look"}
              </Button>
              <Button variant="ghost" disabled={busy} onClick={() => setOpen(false)}>Cancel</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </>
  )
}
