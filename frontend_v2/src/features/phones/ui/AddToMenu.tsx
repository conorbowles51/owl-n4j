import { useEffect, useMemo, useState } from "react"
import { trackUx } from "@/lib/ux-events"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { ProgressPanel } from "@/components/ui/progress-panel"
import { register } from "@/lib/keymap"
import { CONFIRM_OVER } from "@/stores/phone-selection.store"
import { trackBulkAdd } from "../job-list"
import { orderTargets } from "../lib/order-targets"
import {
  addInParts,
  partsNeeded,
  PART_SIZE,
  countNoun,
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
  noDossierWhy,
  kinds,
  description = "Each keeps a link back to its record. Nothing is copied out of the phone.",
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
  /** Why this item does not go straight into a dossier (07 6.1): shown in place of the list of dossiers. */
  noDossierWhy?: string
  /** The places offered, when they are not all of them. */
  kinds?: TargetKind[]
  /** The line under the dialog's title. */
  description?: string
}) {
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState<TargetKind | null>(null)
  const [relationship, setRelationship] = useState<Relationship>("unclassified")
  const [role, setRole] = useState<DossierRole>("link")
  const [confirmBig, setConfirmBig] = useState(false)
  const [progress, setProgress] = useState<{ done: number; total: number; startedAt: number; movedAt: number } | null>(null)
  const [reply, setReply] = useState<{ text: string; target: CollectTarget; result: CollectResult } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const count = links.length
  const offered = kinds ? KIND_KEYS.filter((k) => kinds.includes(k.kind)) : KIND_KEYS
  const ordered = useMemo(() => (kind ? orderTargets(targets, kind) : []), [targets, kind])

  const start = (k: TargetKind, byKey: boolean) => {
    if (disabledReason) return
    setKind(k)
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

  const send = async (target: CollectTarget) => {
    if (confirmBig || progress) return
    const t0 = performance.now()
    setProgress({ done: 0, total: count, startedAt: t0, movedAt: t0 })
    // more than one part takes a while: the job tray keeps its true counts through a reload
    const report = count > PART_SIZE ? await trackBulkAdd(caseId, target.label, noun, count) : null
    let sent = 0
    let sofar: CollectResult = { added: 0, skipped: 0, refused: 0 }
    try {
      const result = await addInParts(client, caseId, target, links, { relationship, role, origin }, (done, total) =>
        setProgress((p) => ({ done, total, startedAt: p?.startedAt ?? t0, movedAt: performance.now() })),
        (done, r) => {
          sent = done
          sofar = r
          void report?.(done, r, done >= count, null)
        }
      )
      setReply({ text: resultSentence(result, noun, target), target, result })
      setOpen(false)
      onAdded?.(target, result)
      trackUx(caseId, { event: "collect", target_kind: target.kind, count, added: result.added, skipped: result.skipped,
        refused: result.refused, ms: performance.now() - t0 })
    } catch (e) {
      void report?.(sent, sofar, true, e instanceof Error ? e.message : "The add stopped")
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
            <DialogTitle>Add {count.toLocaleString("en-US")} {countNoun(count, noun)} to…</DialogTitle>
            <DialogDescription>{description}</DialogDescription>
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
            {offered.map((k) => (
              <Button key={k.kind} size="sm" variant={kind === k.kind ? "secondary" : "outline"} aria-pressed={kind === k.kind} onClick={() => setKind(k.kind)}>
                {k.words} <kbd className="ml-1 text-xs text-muted-foreground">{k.key}</kbd>
              </Button>
            ))}
          </div>
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
          {kind && (
            <div className="flex flex-col gap-1 text-sm">
              <p className="font-medium">{KIND_KEYS.find((k) => k.kind === kind)!.words}</p>
              {kind === "dossier" && noDossierWhy ? <p>{noDossierWhy}</p> : ordered.length === 0 && <p>No {KIND_KEYS.find((k) => k.kind === kind)!.words.toLowerCase()} in this case yet. Create one from Workspace or Dossiers first.</p>}
              {ordered.length > 0 && !(kind === "dossier" && noDossierWhy) && (
                // choosing a target adds to it (07 J-12: one item in 3 actions); the reply offers Undo
                <div role="listbox" aria-label={`Choose where to add: ${KIND_KEYS.find((k) => k.kind === kind)!.words}`} className="flex flex-col gap-0.5">
                  {ordered.map((t) => (
                    <div
                      key={t.id}
                      role="option"
                      aria-selected={false}
                      aria-disabled={confirmBig || !!progress}
                      tabIndex={0}
                      className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 hover:bg-muted aria-disabled:cursor-not-allowed aria-disabled:opacity-60"
                      onClick={() => void send(t)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault()
                          void send(t)
                        }
                      }}
                    >
                      {t.label}
                      {t.linkedPerson && <span className="text-xs text-muted-foreground">(linked person)</span>}
                      {t.recent && !t.linkedPerson && <span className="text-xs text-muted-foreground">(recent)</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
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
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
