import { useEffect, useMemo, useState } from "react"
import { trackUx } from "@/lib/ux-events"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { ProgressPanel } from "@/components/ui/progress-panel"
import { register } from "@/lib/keymap"
import { CONFIRM_OVER } from "@/stores/phone-selection.store"
import { orderTargets } from "../lib/order-targets"
import {
  addInParts,
  partsNeeded,
  PART_SIZE,
  resultSentence,
  type CollectClient,
  type CollectLink,
  type CollectResult,
  type CollectTarget,
  type DossierRole,
  type Relationship,
  type TargetKind,
} from "../collect.api"

/**
 * Add to… (07 J-12, 6.2): one menu on every row, point, hit, thread, file and result. `c` opens it, then d / w / n
 * / t / l picks dossier, finding or theory, note, Timeline or label. Recent targets come first and a linked
 * person's dossier is offered first. A finding asks for Supports, Contradicts, Context or Unclassified; a dossier
 * asks for a role. Large selections go in stated parts with a progress panel, and the reply gives added,
 * already-there and refused counts with Undo. A key-triggered add of more than 5,000 records asks first.
 */
const KIND_KEYS: { kind: TargetKind; key: string; words: string }[] = [
  { kind: "dossier", key: "d", words: "Dossier" },
  { kind: "finding", key: "w", words: "Finding or theory" },
  { kind: "note", key: "n", words: "Note" },
  { kind: "timeline", key: "t", words: "Timeline" },
  { kind: "label", key: "l", words: "Label" },
]

const RELATIONSHIPS: { id: Relationship; words: string }[] = [
  { id: "supports", words: "Supports" },
  { id: "contradicts", words: "Contradicts" },
  { id: "context", words: "Context" },
  { id: "unclassified", words: "Unclassified" },
]
const ROLES: { id: DossierRole; words: string }[] = [
  { id: "link", words: "Link" },
  { id: "contact", words: "Contact" },
  { id: "photo", words: "Photo" },
  { id: "assessment_support", words: "Assessment support" },
  { id: "interview_evidence", words: "Interview evidence" },
]


export function AddToMenu({
  caseId,
  links,
  noun,
  targets,
  client,
  origin,
  onUndo,
  onAdded,
  disabledReason,
  keys = true,
}: {
  caseId: string
  /** What is selected, as links (a selection over 500 arrives as one phone_selection link, 07 6.1). */
  links: CollectLink[]
  noun: string
  targets: CollectTarget[]
  client: CollectClient
  /** Where it was added from, e.g. "Added from Conversations". */
  origin: string
  onUndo?: (target: CollectTarget, result: CollectResult) => void
  /** Called after a successful add (e.g. to refresh "In 2 dossiers" on the rows). */
  onAdded?: (target: CollectTarget, result: CollectResult) => void
  /** Set when the person may not add here: the control is disabled and states why (07 4.11). */
  disabledReason?: string
  keys?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState<TargetKind | null>(null)
  const [target, setTarget] = useState<CollectTarget | null>(null)
  const [relationship, setRelationship] = useState<Relationship>("unclassified")
  const [role, setRole] = useState<DossierRole>("link")
  const [confirmBig, setConfirmBig] = useState(false)
  const [progress, setProgress] = useState<{ done: number; total: number; startedAt: number; movedAt: number } | null>(null)
  const [reply, setReply] = useState<{ text: string; target: CollectTarget; result: CollectResult } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const count = links.length
  const ordered = useMemo(() => (kind ? orderTargets(targets, kind) : []), [targets, kind])

  const start = (k: TargetKind, byKey: boolean) => {
    if (disabledReason) return
    setKind(k)
    setTarget(null)
    setReply(null)
    setError(null)
    setConfirmBig(byKey && count > CONFIRM_OVER)
    setOpen(true)
  }

  useEffect(() => {
    if (!keys || disabledReason) return
    return register("Add to…", [
      ...KIND_KEYS.map((k) => ({ key: `c ${k.key}`, label: `Add to: ${k.words}`, run: () => start(k.kind, true) })),
    ])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keys, disabledReason, count])

  const send = async () => {
    if (!target) return
    const t0 = performance.now()
    setProgress({ done: 0, total: count, startedAt: t0, movedAt: t0 })
    try {
      const result = await addInParts(client, caseId, target, links, { relationship, role, origin }, (done, total) =>
        setProgress((p) => ({ done, total, startedAt: p?.startedAt ?? t0, movedAt: performance.now() }))
      )
      setReply({ text: resultSentence(result, noun, target), target, result })
      setOpen(false)
      onAdded?.(target, result)
      trackUx(caseId, { event: "collect", target_kind: target.kind, count, added: result.added, skipped: result.skipped,
        refused: result.refused, ms: performance.now() - t0 })
    } catch (e) {
      setError(`${e instanceof Error ? e.message : "The add stopped"}. Your ${count.toLocaleString("en-US")} ${noun} are still selected. Add them again.`)
    } finally {
      setProgress(null)
    }
  }

  return (
    <div className="inline-flex flex-col gap-1">
      <div className="inline-flex flex-wrap items-center gap-1">
        <Button size="sm" onClick={() => start(kind ?? "finding", false)} disabled={!!disabledReason || count === 0} title={disabledReason}>
          Add to…
        </Button>
        {disabledReason && <span className="text-sm text-muted-foreground">{disabledReason}</span>}
      </div>
      {reply && (
        <p role="status" className="text-sm">
          {reply.text}{" "}
          {onUndo && reply.result.added > 0 && (
            <button type="button" className="underline underline-offset-2" onClick={() => (onUndo(reply.target, reply.result), setReply(null))}>
              Undo
            </button>
          )}
        </p>
      )}
      <Dialog open={open} onOpenChange={(v) => !progress && setOpen(v)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add {count.toLocaleString("en-US")} {noun} to…</DialogTitle>
            <DialogDescription>Each keeps a link back to its record. Nothing is copied out of the phone.</DialogDescription>
          </DialogHeader>
          {confirmBig && (
            <div role="alert" className="rounded border border-status-review p-2 text-sm">
              <p>
                You pressed a key to add {count.toLocaleString("en-US")} {noun}. That is more than {CONFIRM_OVER.toLocaleString("en-US")}.
              </p>
              <Button size="sm" variant="outline" className="mt-1" onClick={() => setConfirmBig(false)}>
                Yes, add all {count.toLocaleString("en-US")}
              </Button>
            </div>
          )}
          <div role="group" aria-label="Where to add" className="flex flex-wrap gap-1">
            {KIND_KEYS.map((k) => (
              <Button key={k.kind} size="sm" variant={kind === k.kind ? "secondary" : "outline"} aria-pressed={kind === k.kind} onClick={() => (setKind(k.kind), setTarget(null))}>
                {k.words} <kbd className="ml-1 text-xs text-muted-foreground">{k.key}</kbd>
              </Button>
            ))}
          </div>
          {kind && (
            <fieldset className="flex flex-col gap-1 text-sm">
              <legend className="mb-1 font-medium">{KIND_KEYS.find((k) => k.kind === kind)!.words}</legend>
              {ordered.length === 0 && <p>No {KIND_KEYS.find((k) => k.kind === kind)!.words.toLowerCase()} in this case yet. Create one from Workspace or Dossiers first.</p>}
              {ordered.map((t) => (
                <label key={t.id} className="flex items-center gap-2">
                  <input type="radio" name="add-target" checked={target?.id === t.id} onChange={() => setTarget(t)} />
                  {t.label}
                  {t.linkedPerson && <span className="text-xs text-muted-foreground">(linked person)</span>}
                  {t.recent && !t.linkedPerson && <span className="text-xs text-muted-foreground">(recent)</span>}
                </label>
              ))}
            </fieldset>
          )}
          {(kind === "finding" || kind === "note") && (
            <label className="flex items-center gap-2 text-sm">
              How it relates
              <select className="rounded border bg-card px-1 py-0.5" value={relationship} onChange={(e) => setRelationship(e.target.value as Relationship)}>
                {RELATIONSHIPS.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.words}
                  </option>
                ))}
              </select>
            </label>
          )}
          {kind === "dossier" && (
            <label className="flex items-center gap-2 text-sm">
              Role in the dossier
              <select className="rounded border bg-card px-1 py-0.5" value={role} onChange={(e) => setRole(e.target.value as DossierRole)}>
                {ROLES.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.words}
                  </option>
                ))}
              </select>
            </label>
          )}
          {count > PART_SIZE && (
            <p className="text-sm">
              Links are added {PART_SIZE.toLocaleString("en-US")} at a time; {count.toLocaleString("en-US")} selected. Adding in {partsNeeded(count)} parts. Nothing is cut.
            </p>
          )}
          {progress && (
            <ProgressPanel
              progress={{ step: `Linking ${noun}`, done: progress.done, total: progress.total, unit: noun, startedAt: progress.startedAt, movedAt: progress.movedAt }}
              now={performance.now()}
            />
          )}
          {error && (
            <p role="alert" className="text-sm text-status-error">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={!!progress}>
              Cancel
            </Button>
            <Button onClick={() => void send()} disabled={!target || confirmBig || !!progress}>
              Add {count.toLocaleString("en-US")} {noun}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
