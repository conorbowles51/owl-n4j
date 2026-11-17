import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { corroborateAPI } from "./api"
import { addPart, selectionMembers, useSelection } from "./selection-store"

const OPS = [["both", "in both"], ["either", "in either"], ["a_not_b", "in the first, not the second"], ["b_not_a", "in the second, not the first"]] as const

/**
 * Saved subsets and set operations (lx-corroselect D, Q): name the selection to keep it, bring one back, or combine two
 * (in both, in either, in one but not the other). The result joins the selection with both sides' counts stated.
 */
export function SavedSubsets({ caseId, onClose }: { caseId: string; onClose: () => void }) {
  const parts = useSelection(caseId)
  const members = selectionMembers(parts)
  const qc = useQueryClient()
  const list = useQuery({ queryKey: ["corroborate-subsets", caseId], queryFn: () => corroborateAPI.subsets(caseId) })
  const [name, setName] = useState("")
  const [a, setA] = useState("")
  const [b, setB] = useState("")
  const [op, setOp] = useState<(typeof OPS)[number][0]>("both")
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const subsets = list.data?.subsets ?? []
  const attempt = async (f: () => Promise<string>) => {
    setBusy(true)
    setNote(null)
    try {
      setNote(await f())
    } catch (e) {
      setNote(e instanceof Error ? e.message : "That failed. Nothing was changed.")
    } finally {
      setBusy(false)
    }
  }
  return (
    <Dialog open onOpenChange={(o) => !o && !busy && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Saved subsets</DialogTitle>
          <DialogDescription>Keep what you have selected under a name, bring it back later, or combine two.</DialogDescription>
        </DialogHeader>
        <div className="flex items-end gap-2">
          <label className="flex flex-1 flex-col text-sm">Save the {members.length.toLocaleString("en-US")} selected items as
            <input className="rounded border bg-card px-2 py-1" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
          </label>
          <Button size="sm" disabled={busy || !name.trim() || members.length === 0} onClick={() => void attempt(async () => {
            const saved = await corroborateAPI.saveSubset(caseId, name.trim(), members)
            void qc.invalidateQueries({ queryKey: ["corroborate-subsets", caseId] })
            setName("")
            return `Saved ${saved.member_count.toLocaleString("en-US")} items.`
          })}>Save</Button>
        </div>
        {list.isLoading && <p role="status" className="text-sm">Loading saved subsets…</p>}
        {!list.isLoading && subsets.length === 0 && <p className="text-sm">No saved subsets in this case yet.</p>}
        {subsets.length >= 1 && (
          <div className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
            <select aria-label="First subset" className="rounded border bg-card px-1 py-1" value={a} onChange={(e) => setA(e.target.value)}>
              <option value="">First…</option>
              {subsets.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.member_count.toLocaleString("en-US")})</option>)}
            </select>
            <select aria-label="How to combine" className="rounded border bg-card px-1 py-1" value={op} onChange={(e) => setOp(e.target.value as typeof op)}>
              {OPS.map(([v, w]) => <option key={v} value={v}>{w}</option>)}
            </select>
            <select aria-label="Second subset" className="rounded border bg-card px-1 py-1" value={b} onChange={(e) => setB(e.target.value)}>
              <option value="">Second…</option>
              {subsets.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.member_count.toLocaleString("en-US")})</option>)}
            </select>
          </div>
        )}
        {note && <p role="status" className="text-sm">{note}</p>}
        <DialogFooter className="gap-2">
          {subsets.length >= 1 && (
            <Button disabled={busy || !a} onClick={() => void attempt(async () => {
              const second = b || a
              const got = await corroborateAPI.combine(caseId, a, second, op)
              if (!got.count) return `Nothing is ${got.words}: the first has ${got.first.toLocaleString("en-US")}, the second ${got.second.toLocaleString("en-US")}.`
              addPart(caseId, { screen: "saved subsets", label: `${subsets.find((s) => s.id === a)?.name} ${got.words} ${subsets.find((s) => s.id === second)?.name} (${got.count.toLocaleString("en-US")})`, members: got.members, skipped: [] })
              return `${got.count.toLocaleString("en-US")} items ${got.words} added to the selection (first ${got.first.toLocaleString("en-US")}, second ${got.second.toLocaleString("en-US")}).`
            })}>{b ? "Combine into the selection" : "Add the first to the selection"}</Button>
          )}
          <Button variant="ghost" onClick={onClose} disabled={busy}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
