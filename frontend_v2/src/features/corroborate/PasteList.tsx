import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { corroborateAPI, type ListMatch } from "./api"
import { addPart } from "./selection-store"

/** A pasted list of numbers, accounts, plates or e-mails, each matched to the case; the unmatched are listed (lx-corroselect C). */
export function PasteList({ caseId, onClose, onDone }: { caseId: string; onClose: () => void; onDone: () => void }) {
  const [text, setText] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ListMatch | null>(null)
  const match = async () => {
    setBusy(true)
    setError(null)
    try {
      setResult(await corroborateAPI.matchList(caseId, text))
    } catch (e) {
      setError(e instanceof Error ? e.message : "The list could not be matched.")
    } finally {
      setBusy(false)
    }
  }
  const use = () => {
    if (!result) return
    addPart(caseId, {
      screen: "a pasted list",
      label: `Pasted list (${result.matched} of ${result.tokens.length} matched)`,
      members: result.members,
      skipped: [],
      unmatched: result.unmatched.map((u) => u.token),
    })
    onDone()
  }
  return (
    <Dialog open onOpenChange={(o) => !o && !busy && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Paste a list</DialogTitle>
          <DialogDescription>Phone numbers, account numbers or plates, one per line or separated by commas. Loupe matches each to the case.</DialogDescription>
        </DialogHeader>
        <textarea aria-label="List to match" className="min-h-32 rounded border bg-card px-2 py-1 text-sm" value={text} onChange={(e) => { setText(e.target.value); setResult(null) }} />
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {result && (
          <div role="status" className="flex flex-col gap-1 text-sm">
            <p>{result.matched} of {result.tokens.length} entries matched, {result.members.length.toLocaleString("en-US")} items in the case.</p>
            {result.unmatched.length > 0 && (
              <div>
                <p>Not matched:</p>
                <ul className="list-disc pl-5">
                  {result.unmatched.map((u) => <li key={u.token}>{u.token}: {u.unmatched_reason}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}
        <DialogFooter className="gap-2">
          {result ? <Button disabled={!result.members.length} disabledReason="Nothing in the list matched the case. Change the list and match it again." onClick={use}>Add {result.members.length.toLocaleString("en-US")} items to the selection</Button>
            : <Button disabled={busy || !text.trim()} onClick={() => void match()}>{busy ? "Matching…" : "Match to the case"}</Button>}
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
