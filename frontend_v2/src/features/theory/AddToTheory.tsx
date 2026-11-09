import { useMemo, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useCollectTargets } from "@/features/phones/collect-targets"
import { theoryHref } from "./source-links"
import { announce } from "@/features/guidance/announce"
import { theoryAPI, choiceWords, type AdditionInput, type AdditionResult, type GroupInput, type ItemInput, type Surface } from "./api"

/**
 * "Add to theory…" (lx-theorybuild A, G): one control on every surface, for one item or a group. What is added
 * becomes a unit of the theory that knows why it was chosen: the dialog states what goes in ("12 items from the
 * ledger, chosen: payments under 100"), asks why in the person's words, and takes the person's own account of what
 * it shows, or asks the model for one (saved as a model reading, labelled as such until a person confirms it).
 * It adds to an existing theory, finding or note, or starts a new theory from this. Undo removes exactly what was
 * added. No crypto or clipboard APIs: the site runs on plain http.
 */
export interface AddToTheoryProps {
  caseId: string
  surface: Surface
  /** One or more single items (each becomes its own addition). */
  items?: ItemInput[]
  /** Or a group, stored once with every member and how it was chosen. */
  group?: GroupInput
  /** Button words; defaults to "Add to theory…". */
  label?: string
  size?: "sm" | "default"
  disabledReason?: string
}

export function AddToTheory({ caseId, surface, items, group, label = "Add to theory…", size = "sm", disabledReason }: AddToTheoryProps) {
  const [open, setOpen] = useState(false)
  const count = group ? group.members.length : (items?.length ?? 0)
  const nothing = count === 0
  return (
    <span className="inline-flex flex-col gap-1">
      <Button
        size={size}
        variant="outline"
        onClick={() => setOpen(true)}
        disabled={nothing || !!disabledReason}
        title={disabledReason || (nothing ? "Nothing is selected" : `Add ${choiceWords(count, surface)} to a theory`)}
      >
        {label}
      </Button>
      {open && <AddToTheoryDialog caseId={caseId} surface={surface} items={items} group={group} onClose={() => setOpen(false)} />}
    </span>
  )
}

export function AddToTheoryDialog({ caseId, surface, items, group, onClose }: Omit<AddToTheoryProps, "label" | "size"> & { onClose: () => void }) {
  const qc = useQueryClient()
  const t = useCollectTargets(caseId)
  const [why, setWhy] = useState(group?.words ?? "")
  const [narrative, setNarrative] = useState("")
  const [askModel, setAskModel] = useState(false)
  const [newTitle, setNewTitle] = useState("")
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<{ result: AdditionResult; target: string; entryId: string; note?: string } | null>(null)
  const count = group ? group.members.length : (items?.length ?? 0)
  const targets = useMemo(() => {
    const order = { theory: 0, finding: 1, note: 2 } as Record<string, number>
    return t.targets.filter((x) => x.kind in order).sort((a, b) => order[a.kind] - order[b.kind])
  }, [t.targets])
  const what = group ? choiceWords(count, surface, group.words) : count === 1 ? (items?.[0]?.target_label || "1 item") : choiceWords(count, surface)

  const body = (): AdditionInput => ({
    surface,
    why: why.trim() || undefined,
    narrative: narrative.trim() || undefined,
    ...(group ? { group: { ...group, words: why.trim() || group.words } } : { items }),
  })

  const after = async (result: AdditionResult, target: string, entryId: string) => {
    let note: string | undefined
    if (askModel && !narrative.trim() && result.added_link_ids.length) {
      setBusy("The model is reading what was added…")
      try {
        for (const linkId of result.added_link_ids) await theoryAPI.infer(caseId, entryId, linkId)
        note = "The model's reading is saved beside it, labelled as a model reading until you confirm it."
      } catch (e) {
        note = `Added, but the model could not write its reading: ${e instanceof Error ? e.message : "it failed"}. Ask again from the theory.`
      }
    }
    setDone({ result, target, entryId, note })
    announce(caseId, { kind: "theory-addition", title: target, entryId, added: result.added, trail: group?.group_type === "step_trail" })
    void qc.invalidateQueries({ queryKey: ["theory-reading", caseId, entryId] })
    void qc.invalidateQueries({ queryKey: ["collect-targets"] })
  }

  const addTo = async (entryId: string, title: string) => {
    if (busy) return
    setBusy(`Adding to ${title}…`)
    setError(null)
    try {
      const result = await theoryAPI.add(caseId, entryId, body())
      await after(result, title, entryId)
    } catch (e) {
      setError(e instanceof Error ? e.message : "The add failed; nothing was added.")
    } finally {
      setBusy(null)
    }
  }

  const startNew = async () => {
    const title = newTitle.trim()
    if (!title || busy) return
    setBusy(`Starting the theory ${title}…`)
    setError(null)
    try {
      const result = await theoryAPI.newTheory(caseId, { ...body(), title })
      await after(result, title, result.entry_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : "The theory was not made.")
    } finally {
      setBusy(null)
    }
  }

  const undo = async () => {
    if (!done) return
    setBusy("Undoing…")
    try {
      await theoryAPI.undo(caseId, done.entryId, done.result.added_link_ids, done.result.version)
      void qc.invalidateQueries({ queryKey: ["theory-reading", caseId, done.entryId] })
      setDone(null)
      setError("Undone: nothing from this add is in the theory now.")
    } catch (e) {
      setError(`Undo failed: ${e instanceof Error ? e.message : "it failed"}`)
    } finally {
      setBusy(null)
    }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && !busy && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add to a theory</DialogTitle>
          <DialogDescription>{what}. It keeps a link to where it came from and why it was chosen.</DialogDescription>
        </DialogHeader>
        {done ? (
          <div role="status" className="flex flex-col gap-2 text-sm">
            <p>
              {done.result.added
                ? `Added ${group ? "the group" : `${done.result.added.toLocaleString("en-US")} ${done.result.added === 1 ? "item" : "items"}`} to ${done.target}.`
                : `Already in ${done.target}; nothing new was added.`}
              {done.result.skipped > 0 && done.result.added > 0 && ` ${done.result.skipped} ${done.result.skipped === 1 ? "was" : "were"} already there.`}
              {done.result.group && done.result.group.left_out > 0 &&
                ` ${done.result.group.left_out.toLocaleString("en-US")} of the chosen items are not in this case and were not kept.`}
            </p>
            {done.note && <p>{done.note}</p>}
            <div className="flex gap-2">
              <a className="underline underline-offset-2" href={theoryHref(caseId, done.entryId)}>
                Open the theory
              </a>
              {done.result.added > 0 && (
                <button type="button" className="underline underline-offset-2" onClick={() => void undo()} disabled={!!busy}>
                  Undo
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-3 text-sm">
            <label className="flex flex-col gap-1">
              Why this, in your words
              <input
                className="rounded border bg-card px-2 py-1"
                value={why}
                maxLength={1000}
                placeholder={group ? "e.g. every payment under 100 in March" : "e.g. the account the money ends in"}
                onChange={(e) => setWhy(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1">
              What it shows (optional)
              <textarea
                className="min-h-16 rounded border bg-card px-2 py-1"
                value={narrative}
                maxLength={8000}
                placeholder="Your own account of what this shows and finds"
                onChange={(e) => setNarrative(e.target.value)}
              />
            </label>
            <label className="flex items-start gap-2">
              <input type="checkbox" checked={askModel} disabled={!!narrative.trim()} onChange={(e) => setAskModel(e.target.checked)} />
              <span>
                Ask the model to write what it shows, citing the items. It is saved as a model reading, with the model's name, until you
                confirm or replace it.
              </span>
            </label>
            <div className="flex flex-col gap-1">
              <p className="font-medium">Add to</p>
              {t.loading && <p className="text-muted-foreground">Loading theories…</p>}
              {!t.loading && targets.length === 0 && <p>No theories, findings or notes in this case yet. Start a new theory below.</p>}
              <div role="listbox" aria-label="Choose the theory" className="flex max-h-56 flex-col gap-0.5 overflow-auto">
                {targets.map((x) => (
                  <div
                    key={x.id}
                    role="option"
                    aria-selected={false}
                    aria-disabled={!!busy}
                    tabIndex={0}
                    className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 hover:bg-muted aria-disabled:cursor-not-allowed aria-disabled:opacity-60"
                    onClick={() => void addTo(x.id, x.label)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault()
                        void addTo(x.id, x.label)
                      }
                    }}
                  >
                    <span className="text-xs uppercase text-muted-foreground">{x.kind}</span>
                    {x.label}
                  </div>
                ))}
              </div>
              {t.note && <p className="text-xs text-muted-foreground">{t.note}</p>}
            </div>
            <div className="flex items-end gap-2">
              <label className="flex flex-1 flex-col gap-1">
                New theory from this
                <input className="rounded border bg-card px-2 py-1" value={newTitle} maxLength={300} placeholder="Name the theory" onChange={(e) => setNewTitle(e.target.value)} />
              </label>
              <Button size="sm" onClick={() => void startNew()} disabled={!newTitle.trim() || !!busy}>
                Start theory
              </Button>
            </div>
          </div>
        )}
        {busy && <p role="status" className="text-sm">{busy}</p>}
        {error && <p role="alert" className="text-sm text-status-error">{error}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={!!busy}>
            {done ? "Close" : "Cancel"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
